#!/usr/bin/env bash
set -euo pipefail

CONTAINER_IMAGE_DOCKER_DEFAULT="ghcr.io/jordissm/electra:latest"
CONTAINER_IMAGE_APPTAINER_DEFAULT=""
PREFIX_DEFAULT="$PWD"

# Default bind dirs (relative to where install.sh is run)
OUTPUT_DEFAULT="$PWD/output"
INPUT_DEFAULT="$PWD/input"
SLURM_SCRIPTS_DEFAULT="$PWD/slurm-scripts"

PREFIX="$PREFIX_DEFAULT"
IMG_DOCKER="$CONTAINER_IMAGE_DOCKER_DEFAULT"
SIF_PATH="$CONTAINER_IMAGE_APPTAINER_DEFAULT"
TMPDIR_OPT="${TMPDIR:-/tmp}"
OUTPUT_DIR="$OUTPUT_DEFAULT"
INPUT_DIR="$INPUT_DEFAULT"
SLURM_SCRIPTS_DIR="$SLURM_SCRIPTS_DEFAULT"
UTILS_DIR=""
BUILD_ANALYSIS="1"

SIF_DIR_DEFAULT="${SIF_DIR_DEFAULT:-/scratch/$USER/containers}"
SIF_NAME_DEFAULT="electra.sif"
PULL_SIF_DEFAULT="0"

SIF_DIR="$SIF_DIR_DEFAULT"
SIF_NAME="$SIF_NAME_DEFAULT"
PULL_SIF="$PULL_SIF_DEFAULT"

print_help() {
  cat <<EOF
USAGE: ./install.sh [OPTIONS]

OPTIONS:
  -p, --prefix <dir>        Installation prefix (default: $PREFIX_DEFAULT)
  -i, --image <ref>         Container image ref (default: $CONTAINER_IMAGE_DOCKER_DEFAULT)
  -s, --sif <path>          Apptainer/Singularity SIF path (optional)
  -t, --tmpdir <dir>        TMPDIR for apptainer/singularity (default: $TMPDIR_OPT)
      --output <dir>        Default host output directory (default: $OUTPUT_DEFAULT)
      --input <dir>         Default host input directory (optional)
      --utils <dir>         Utility install directory (default: <prefix>/utils)
      --skip-analysis-build Copy sources without building the host OSCAR analyzer
  (workdir is set at runtime via electra-shell --workdir; default /workspace)
  --pull-sif              Pull/build a local SIF file at install time (apptainer only)
  --sif-dir <dir>         Directory to store the SIF (default: /scratch/$USER/containers)
  --sif-name <name>       SIF filename (default: electra.sif)
  -h, --help                Show help

What it creates:
  <prefix>/electra-shell
  <prefix>/utils/ (or --utils directory; existing sources are preserved)
  <utils-directory>/analyze_oscar_output (built with host CMake and C++17)

The analysis build privately installs yaml-cpp on first use. For offline builds,
set ELECTRA_YAML_CPP_ARCHIVE to the official 0.8.0 archive or
ELECTRA_YAML_CPP_PREFIX to an existing installation.

Typical usage:
  ./install.sh
  ./electra-shell -- electra --help
  ./electra-shell -- electra pipeline run --run-dir /output/test --nevents 1
EOF
}

realpath_py() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

patch_slurm_scripts() {
  local dir="$1"

  [[ -d "$dir" ]] || return 0

  # Patch eHIJING submit script defaults
  if [[ -f "$dir/ehijing_submit.sh" ]]; then
  sed -i \
    -e "s|^PROJECT_ROOT=.*$|PROJECT_ROOT=\"\${PROJECT_ROOT:-$PREFIX}\"|" \
    -e "s|^CONFIG_PATH=.*$|CONFIG_PATH=\"\${CONFIG_PATH:-$INPUT_DIR/ehijing/experiments/\${EXPERIMENT}/hard_process.setting}\"|" \
    -e "s|^HADRONIZATION_CONFIG_PATH=.*$|HADRONIZATION_CONFIG_PATH=\"\${HADRONIZATION_CONFIG_PATH:-$INPUT_DIR/ehijing/experiments/\${EXPERIMENT}/hadronization.setting}\"|" \
    -e "s|^DIS_CUTS_CONFIG_PATH=.*$|DIS_CUTS_CONFIG_PATH=\"\${DIS_CUTS_CONFIG_PATH:-$INPUT_DIR/ehijing/experiments/\${EXPERIMENT}/dis_cuts.setting}\"|" \
    "$dir/ehijing_submit.sh"
  fi

  # Patch SMASH submit script too, if needed later
  if [[ -f "$dir/smash_submit.sh" ]]; then
    sed -i \
      -e "s|^PROJECT_ROOT=.*$|PROJECT_ROOT=\"\${PROJECT_ROOT:-$PREFIX}\"|" \
      "$dir/smash_submit.sh"
  fi

  if [[ -f "$dir/analysis_submit.sh" ]]; then
    python3 - "$dir/analysis_submit.sh" "$PREFIX" "$UTILS_DIR/analyze_oscar_output" "$OUTPUT_DIR" <<'PY'
from pathlib import Path
import shlex
import sys

path = Path(sys.argv[1])
defaults = {"PROJECT_ROOT": sys.argv[2], "ANALYZER": sys.argv[3], "OUTPUT_HOST": sys.argv[4]}
patched = set()
lines = path.read_text().splitlines(keepends=True)
for index, line in enumerate(lines):
    for key, value in defaults.items():
        if key not in patched and line.startswith(key + "="):
            lines[index] = key + "=${" + key + ":-" + shlex.quote(value) + "}\n"
            patched.add(key)
path.write_text("".join(lines))
PY
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--prefix) PREFIX="$(realpath_py "$2")"; shift 2;;
    -i|--image)  IMG_DOCKER="$2"; shift 2;;
    -s|--sif)    SIF_PATH="$2"; shift 2;;
    -t|--tmpdir) TMPDIR_OPT="$2"; shift 2;;
    --output)    OUTPUT_DIR="$(realpath_py "$2")"; shift 2;;
    --input)     INPUT_DIR="$(realpath_py "$2")"; shift 2;;
    --utils)     UTILS_DIR="$(realpath_py "$2")"; shift 2;;
    --skip-analysis-build) BUILD_ANALYSIS="0"; shift 1;;
    --slurm-scripts) SLURM_SCRIPTS_DIR="$(realpath_py "$2")"; shift 2;;
    --pull-sif)  PULL_SIF="1"; shift 1;;
    --sif-dir)   SIF_DIR="$(realpath_py "$2")"; shift 2;;
    --sif-name)  SIF_NAME="$2"; shift 2;;
    -h|--help)   print_help; exit 0;;
    *) echo "ERROR: unknown arg $1"; echo "Use --help"; exit 1;;
  esac
done

if [[ -z "$UTILS_DIR" ]]; then
  UTILS_DIR="$PREFIX/utils"
fi

mkdir -p "$PREFIX"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$INPUT_DIR"
mkdir -p "$UTILS_DIR"

PROJECT_HOST="$(realpath_py "$PREFIX")"

ON_CLUSTER="0"
if command -v sbatch >/dev/null 2>&1 || command -v srun >/dev/null 2>&1 || [[ -n "${SLURM_CLUSTER_NAME:-}" || -n "${SLURM_JOB_ID:-}" ]]; then
  ON_CLUSTER="1"
  mkdir -p "$SLURM_SCRIPTS_DIR"
fi

# If requested, materialize a SIF now (so jobs don't hit the registry repeatedly)
if [[ "$PULL_SIF" == "1" ]]; then
  if ! command -v apptainer >/dev/null 2>&1; then
    echo "ERROR: --pull-sif requested but 'apptainer' is not in PATH."
    exit 1
  fi

  mkdir -p "$SIF_DIR"
  # If user didn't explicitly set --sif, choose default path under --sif-dir/--sif-name
  if [[ -z "$SIF_PATH" ]]; then
    SIF_PATH="$SIF_DIR/$SIF_NAME"
  fi

  echo "Pulling SIF to: $SIF_PATH"
  echo "From OCI ref: docker://$IMG_DOCKER"

  # Use the install-time TMPDIR for apptainer scratch
  export TMPDIR="$TMPDIR_OPT"
  export APPTAINER_TMPDIR="$TMPDIR_OPT"
  export SINGULARITY_TMPDIR="$TMPDIR_OPT"

  # Only pull if missing (or empty/zero size)
  if [[ ! -s "$SIF_PATH" ]]; then
    apptainer pull "$SIF_PATH" "docker://$IMG_DOCKER"
  else
    echo "SIF already exists, not re-pulling: $SIF_PATH"
  fi

  echo "SIF ready:"
  ls -lh "$SIF_PATH"
  python3 - "$SIF_PATH" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as package:
    for chunk in iter(lambda: package.read(1024 * 1024), b""):
        digest.update(chunk)
print(f"SIF SHA256: {digest.hexdigest()}")
PY
fi

# Populate host input dir with packaged defaults only if empty
if [[ -z "$(find "$INPUT_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  if [[ -n "$SIF_PATH" && -s "$SIF_PATH" ]] && command -v apptainer >/dev/null 2>&1; then
    echo "Copying default input files from SIF into: $INPUT_DIR"
    apptainer exec --bind "$INPUT_DIR:/workspace/input/" "$SIF_PATH" /bin/bash -c \
      'if [[ -d /opt/electra/share/input-defaults ]]; then cp -a /opt/electra/share/input-defaults/. /workspace/input/; fi'
  elif command -v docker >/dev/null 2>&1; then
    echo "Copying default input files from Docker image into: $INPUT_DIR"
    docker run --rm \
      -v "$INPUT_DIR:/workspace/input/" \
      "$IMG_DOCKER" \
      /bin/bash -lc 'if [[ -d /opt/electra/share/input-defaults ]]; then cp -a /opt/electra/share/input-defaults/. /workspace/input/; fi'
  else
    echo "WARNING: could not copy default input files; no SIF or Docker source available."
  fi
else
  echo "Input dir is not empty, not copying defaults: $INPUT_DIR"
fi

# Install missing utilities on every run, preserving existing host files.
if [[ -n "$SIF_PATH" && -s "$SIF_PATH" ]] && command -v apptainer >/dev/null 2>&1; then
  echo "Copying missing utility files from SIF into: $UTILS_DIR"
  apptainer exec --bind "$UTILS_DIR:/workspace/utils/" "$SIF_PATH" /bin/bash -c \
    'if [[ -d /opt/electra/share/utils ]]; then cp -an /opt/electra/share/utils/. /workspace/utils/; else echo "WARNING: packaged utilities are unavailable in this image." >&2; fi'
elif [[ -n "$SIF_PATH" && -s "$SIF_PATH" ]] && command -v singularity >/dev/null 2>&1; then
  echo "Copying missing utility files from SIF into: $UTILS_DIR"
  singularity exec --bind "$UTILS_DIR:/workspace/utils/" "$SIF_PATH" /bin/bash -c \
    'if [[ -d /opt/electra/share/utils ]]; then cp -an /opt/electra/share/utils/. /workspace/utils/; else echo "WARNING: packaged utilities are unavailable in this image." >&2; fi'
elif command -v docker >/dev/null 2>&1; then
  echo "Copying missing utility files from Docker image into: $UTILS_DIR"
  docker run --rm \
    -v "$UTILS_DIR:/workspace/utils/" \
    "$IMG_DOCKER" \
    /bin/bash -c 'if [[ -d /opt/electra/share/utils ]]; then cp -an /opt/electra/share/utils/. /workspace/utils/; else echo "WARNING: packaged utilities are unavailable in this image." >&2; fi'
else
  echo "WARNING: could not copy utility files; no SIF or Docker source available."
fi

if [[ "$BUILD_ANALYSIS" == "1" ]]; then
  if [[ ! -f "$UTILS_DIR/build_analysis.sh" ]]; then
    echo "ERROR: analysis build script not found: $UTILS_DIR/build_analysis.sh" >&2
    echo "Use an image containing the updated utilities, or deploy the complete utils directory." >&2
    echo "To defer compilation, rerun install.sh with --skip-analysis-build." >&2
    exit 1
  fi
  echo "Building the host OSCAR analyzer in: $UTILS_DIR"
  bash "$UTILS_DIR/build_analysis.sh"
else
  echo "Skipped analysis build. Build later with: bash $UTILS_DIR/build_analysis.sh"
fi

if [[ "$ON_CLUSTER" == "1" ]]; then
  if [[ -z "$(find "$SLURM_SCRIPTS_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    if [[ -n "$SIF_PATH" && -s "$SIF_PATH" ]] && command -v apptainer >/dev/null 2>&1; then
      echo "Copying SLURM scripts from SIF into: $SLURM_SCRIPTS_DIR"
      apptainer exec --bind "$SLURM_SCRIPTS_DIR:/workspace/input/" "$SIF_PATH" \
        /bin/bash -c 'if [[ -d /opt/electra/share/slurm-scripts ]]; then cp -a /opt/electra/share/slurm-scripts/. /workspace/input/; fi'
    elif command -v docker >/dev/null 2>&1; then
      echo "Copying SLURM scripts from Docker image into: $SLURM_SCRIPTS_DIR"
      docker run --rm \
        -v "$SLURM_SCRIPTS_DIR:/workspace/input/" \
        "$IMG_DOCKER" \
        /bin/bash -c 'if [[ -d /opt/electra/share/slurm-scripts ]]; then cp -a /opt/electra/share/slurm-scripts/. /workspace/input/; fi'
    else
      echo "WARNING: could not copy SLURM scripts; no SIF or Docker source available."
    fi
  else
    echo "SLURM scripts dir is not empty, not copying defaults: $SLURM_SCRIPTS_DIR"
  fi
  patch_slurm_scripts "$SLURM_SCRIPTS_DIR"
fi

cat > "$PREFIX/electra-shell" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# --- captured config ---
IMG_DOCKER="$IMG_DOCKER"
SIF_PATH="$SIF_PATH"
TMPDIR_OPT="$TMPDIR_OPT"
OUTPUT_DIR="$OUTPUT_DIR"
INPUT_DIR="$INPUT_DIR"
PROJECT_HOST="$PROJECT_HOST"

print_help() {
  cat <<'HLP'
USAGE: ./electra-shell [OPTIONS] [--] [COMMAND...]

OPTIONS:
  --output <dir>    Host directory bound to /output (default captured at install time)
  --input <dir>     Host directory bound to /input (optional)
  --workdir <path>  Container working directory (default: /workspace)
  -h, --help        Show help

Examples:
  ./electra-shell -- electra --help
  ./electra-shell -- electra pipeline run --run-dir /output/run1 --nevents 1
HLP
}

if [[ "\${1:-}" == "-h" || "\${1:-}" == "--help" ]]; then
  print_help
  exit 0
fi

# Parse launcher options
OUTPUT="\$OUTPUT_DIR"
INPUT="\$INPUT_DIR"
WORKDIR="/workspace"

while [[ \$# -gt 0 ]]; do
  case "\$1" in
    --output) OUTPUT="\$2"; shift 2;;
    --input)  INPUT="\$2"; shift 2;;
    --workdir) WORKDIR="\$2"; shift 2;;
    --) shift; break;;
    *) break;;
  esac
done

CMD=( "\$@" )

ENGINE=""
if command -v apptainer >/dev/null 2>&1; then
  ENGINE="apptainer"
elif command -v singularity >/dev/null 2>&1; then
  ENGINE="singularity"
elif command -v docker >/dev/null 2>&1; then
  ENGINE="docker"
else
  echo "ERROR: Need apptainer/singularity or docker in PATH."
  exit 1
fi

export TMPDIR="\$TMPDIR_OPT"
export SINGULARITY_TMPDIR="\$TMPDIR_OPT"
export APPTAINER_TMPDIR="\$TMPDIR_OPT"

BIND_OUTPUT="\$OUTPUT:/workspace/output"
BIND_INPUT="\$INPUT:/workspace/input"

if [[ "\$ENGINE" == "docker" ]]; then

  DOCKER_CTX="\$(docker context show 2>/dev/null || true)"
  [[ -z "\$DOCKER_CTX" ]] && DOCKER_CTX="default"

  if ! docker image inspect "\$IMG_DOCKER" >/dev/null 2>&1; then
    if docker --context desktop-linux image inspect "\$IMG_DOCKER" >/dev/null 2>&1; then
      DOCKER_CTX="desktop-linux"
    fi
  fi

  DOCKER=(docker --context "\$DOCKER_CTX")

  PULL_FLAG="--pull=missing"
  [[ "\$IMG_DOCKER" != *"/"* ]] && PULL_FLAG="--pull=never"

  PLATFORM_FLAG=""

  if [[ "\${#CMD[@]}" -eq 0 ]]; then
    "\${DOCKER[@]}" run \$PULL_FLAG \${PLATFORM_FLAG:-} -it --rm \\
      -v "\$BIND_OUTPUT" \\
      \$( [[ -n "\$BIND_INPUT" ]] && echo -v "\$BIND_INPUT" ) \\
      -w "\$WORKDIR" \\
      "\$IMG_DOCKER" \\
      /bin/bash
  else
    "\${DOCKER[@]}" run \$PULL_FLAG \${PLATFORM_FLAG:-} -it --rm \\
      -v "\$BIND_OUTPUT" \\
      \$( [[ -n "\$BIND_INPUT" ]] && echo -v "\$BIND_INPUT" ) \\
      -w "\$WORKDIR" \\
      "\$IMG_DOCKER" \\
      "\${CMD[@]}"
  fi
  exit 0
fi

# Apptainer/Singularity
SIF="\$SIF_PATH"
[[ -z "\$SIF" ]] && SIF="docker://\$IMG_DOCKER"

BIND_ARGS=(
  "--bind" "\$PROJECT_HOST:\$PROJECT_HOST"
  "--bind" "\$OUTPUT:\$OUTPUT"
  "--bind" "\$BIND_OUTPUT" 
)

if [[ -n "\$INPUT" ]]; then
  BIND_ARGS+=(
    "--bind" "\$INPUT:\$INPUT"
    "--bind" "\$BIND_INPUT"
  )
fi

if [[ "\${#CMD[@]}" -eq 0 ]]; then
  "\$ENGINE" exec --pwd "\$WORKDIR" "\${BIND_ARGS[@]}" "\$SIF" \
  /usr/local/bin/entrypoint.sh \
  /bin/bash --noprofile --norc -lc "cd \"\$WORKDIR\" && exec /bin/bash --noprofile --norc"
else
  # Quote CMD safely into a shell command for bash -lc
  printf -v _cmd '%q ' "\${CMD[@]}"
  "\$ENGINE" exec --pwd "\$WORKDIR""\${BIND_ARGS[@]}" "\$SIF" \
  /usr/local/bin/entrypoint.sh \
  /bin/bash --noprofile --norc -lc "cd \"\$WORKDIR\" && exec \$_cmd"
fi
EOF

chmod +x "$PREFIX/electra-shell"

echo "Environment setup successful."
echo "Launcher created at: $PREFIX/electra-shell"
echo "Default output dir: $OUTPUT_DIR"
echo "Default input dir:  $INPUT_DIR"
echo "Utility directory:  $UTILS_DIR"
if [[ "$BUILD_ANALYSIS" == "1" ]]; then
  echo "OSCAR analyzer:     $UTILS_DIR/analyze_oscar_output"
fi
echo "Rebuild analysis:   bash $UTILS_DIR/build_analysis.sh"
echo "Run: $PREFIX/electra-shell -- electra --help"
