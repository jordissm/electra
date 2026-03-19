#!/usr/bin/env bash
set -euo pipefail

CONTAINER_IMAGE_DOCKER_DEFAULT="ghcr.io/jordissm/electra:latest"
CONTAINER_IMAGE_APPTAINER_DEFAULT=""
PREFIX_DEFAULT="$PWD"

# Default bind dirs (relative to where install.sh is run)
OUTPUT_DEFAULT="$PWD/output"
INPUT_DEFAULT=""

PREFIX="$PREFIX_DEFAULT"
IMG_DOCKER="$CONTAINER_IMAGE_DOCKER_DEFAULT"
SIF_PATH="$CONTAINER_IMAGE_APPTAINER_DEFAULT"
TMPDIR_OPT="${TMPDIR:-/tmp}"
OUTPUT_DIR="$OUTPUT_DEFAULT"
INPUT_DIR="$INPUT_DEFAULT"

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
  -p, --prefix <dir>        Where to write electra-shell (default: $PREFIX_DEFAULT)
  -i, --image <ref>         Container image ref (default: $CONTAINER_IMAGE_DOCKER_DEFAULT)
  -s, --sif <path>          Apptainer/Singularity SIF path (optional)
  -t, --tmpdir <dir>        TMPDIR for apptainer/singularity (default: $TMPDIR_OPT)
      --output <dir>        Default host output directory (default: $OUTPUT_DEFAULT)
      --input <dir>         Default host input directory (optional)
  (workdir is set at runtime via electra-shell --workdir; default /workspace)
  --pull-sif              Pull/build a local SIF file at install time (apptainer only)
  --sif-dir <dir>         Directory to store the SIF (default: /scratch/$USER/containers)
  --sif-name <name>       SIF filename (default: electra.sif)
  -h, --help                Show help

What it creates:
  <prefix>/electra-shell

Typical usage:
  ./install.sh
  ./electra-shell -- electra --help
  ./electra-shell -- electra pipeline run --run-dir /output/test --nevents 1
EOF
}

realpath_py() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--prefix) PREFIX="$(realpath_py "$2")"; shift 2;;
    -i|--image)  IMG_DOCKER="$2"; shift 2;;
    -s|--sif)    SIF_PATH="$2"; shift 2;;
    -t|--tmpdir) TMPDIR_OPT="$2"; shift 2;;
    --output)    OUTPUT_DIR="$(realpath_py "$2")"; shift 2;;
    --input)     INPUT_DIR="$(realpath_py "$2")"; shift 2;;
    --pull-sif)  PULL_SIF="1"; shift 1;;
    --sif-dir)   SIF_DIR="$(realpath_py "$2")"; shift 2;;
    --sif-name)  SIF_NAME="$2"; shift 2;;
    -h|--help)   print_help; exit 0;;
    *) echo "ERROR: unknown arg $1"; echo "Use --help"; exit 1;;
  esac
done

mkdir -p "$PREFIX"
mkdir -p "$OUTPUT_DIR"
if [[ -n "$INPUT_DIR" ]]; then
  mkdir -p "$INPUT_DIR"
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

mkdir -p "\$OUTPUT"
BIND_OUTPUT="\$OUTPUT:/workspace/output"

BIND_INPUT=""
if [[ -n "\$INPUT" ]]; then
  mkdir -p "\$INPUT"
  BIND_INPUT="\$INPUT:/input"
fi

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
  # HOST_ARCH="\$(uname -m)"
  # if [[ "\$HOST_ARCH" == "arm64" ]]; then
  #   IMG_ARCH="\$(\"\${DOCKER[@]}\" image inspect \"\$IMG_DOCKER\" --format '{{.Architecture}}' 2>/dev/null || true)"
  #   if [[ "\$IMG_ARCH" == "amd64" || "\$IMG_ARCH" == "x86_64" ]]; then
  #     PLATFORM_FLAG="--platform linux/amd64"
  #   fi
  # fi

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

BIND_ARGS=( "--bind" "\$BIND_OUTPUT" )
[[ -n "\$BIND_INPUT" ]] && BIND_ARGS+=( "--bind" "\$BIND_INPUT" )

if [[ "\${#CMD[@]}" -eq 0 ]]; then
  "\$ENGINE" exec "\${BIND_ARGS[@]}" "\$SIF" \
  /usr/local/bin/entrypoint.sh \
  /bin/bash --noprofile --norc -lc "cd \"\$WORKDIR\" && exec /bin/bash --nprofile --norc"
else
  # Quote CMD safely into a shell command for bash -lc
  printf -v _cmd '%q ' "\${CMD[@]}"
  "\$ENGINE" exec "\${BIND_ARGS[@]}" "\$SIF" \
  /usr/local/bin/entrypoint.sh \
  /bin/bash --noprofile --norc -lc "cd \"\$WORKDIR\" && exec \$_cmd"
fi
EOF

chmod +x "$PREFIX/electra-shell"

echo "Environment setup successful."
echo "Launcher created at: $PREFIX/electra-shell"
echo "Default output dir: $OUTPUT_DIR"
[[ -n "$INPUT_DIR" ]] && echo "Default input dir:  $INPUT_DIR"
echo "Run: $PREFIX/electra-shell -- electra --help"