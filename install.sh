#!/usr/bin/env bash
set -euo pipefail

CONTAINER_IMAGE_DOCKER_DEFAULT="ghcr.io/jordissm/electra:latest"   # change
CONTAINER_IMAGE_APPTAINER_DEFAULT=""                              # optional .sif path
PREFIX_DEFAULT="$PWD"

PREFIX="$PREFIX_DEFAULT"
IMG_DOCKER="$CONTAINER_IMAGE_DOCKER_DEFAULT"
SIF_PATH="$CONTAINER_IMAGE_APPTAINER_DEFAULT"
TMPDIR_OPT="${TMPDIR:-/tmp}"

print_help() {
  cat <<EOF
USAGE: ./install.sh [OPTIONS]

OPTIONS:
  -p, --prefix <dir>        Install prefix for launcher (default: $PREFIX_DEFAULT)
  -i, --image <ref>         Docker image ref (default: $CONTAINER_IMAGE_DOCKER_DEFAULT)
  -s, --sif <path>          Apptainer/Singularity SIF path (optional; if empty uses 'docker://' pull at runtime)
  -t, --tmpdir <dir>        Set TMPDIR and SINGULARITY_TMPDIR (default: $TMPDIR_OPT)
  -h, --help                Show help

What it creates:
  <prefix>/electra-shell    A launcher that runs your repo inside Docker (local) or Apptainer/Singularity (cluster).

Examples:
  ./install.sh
  ./install.sh --image ghcr.io/jordissm/electra:latest
  ./electra-shell
  ./electra-shell -- ./electra pipeline run --run-dir runs/test --nevents 10 --nreplicas 5 --profiles-index input/smash/xsec_scaling_factor_profiles/profiles.jsonl
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--prefix) PREFIX="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$2")"; shift 2;;
    -i|--image)  IMG_DOCKER="$2"; shift 2;;
    -s|--sif)    SIF_PATH="$2"; shift 2;;
    -t|--tmpdir) TMPDIR_OPT="$2"; shift 2;;
    -h|--help)   print_help; exit 0;;
    *) echo "ERROR: unknown arg $1"; echo "Use --help"; exit 1;;
  esac
done

mkdir -p "$PREFIX"

cat > "$PREFIX/electra-shell" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# --- captured config from install.sh ---
PREFIX="$PREFIX"
IMG_DOCKER="$IMG_DOCKER"
SIF_PATH="$SIF_PATH"
TMPDIR_OPT="$TMPDIR_OPT"

REPO_ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
# If electra-shell installed outside the repo, prefer current working dir if it contains electra.
if [[ -f "\$PWD/electra" ]]; then
  REPO_ROOT="\$PWD"
fi

print_help() {
  cat <<'HLP'
USAGE: ./electra-shell [--] [COMMAND...]

Examples:
  # interactive shell inside container
  ./electra-shell

  # run one command inside container
  ./electra-shell -- ./electra --help
  ./electra-shell -- ./electra pipeline run ...

Notes:
  - The repo is mounted at /workspace inside the container
  - You should put run outputs under /workspace/runs/... (i.e., relative paths under the workspace)
HLP
}

if [[ "\${1:-}" == "-h" || "\${1:-}" == "--help" ]]; then
  print_help
  exit 0
fi

# Everything after '--' is treated as the command to run in the container
CMD=()
if [[ "\${1:-}" == "--" ]]; then
  shift
  CMD=( "\$@" )
fi

# Prefer apptainer/singularity if present (cluster), else docker (local)
ENGINE=""
if command -v apptainer >/dev/null 2>&1; then
  ENGINE="apptainer"
elif command -v singularity >/dev/null 2>&1; then
  ENGINE="singularity"
elif command -v docker >/dev/null 2>&1; then
  ENGINE="docker"
else
  echo "ERROR: Need apptainer/singularity (cluster) or docker (local) in PATH."
  exit 1
fi

export TMPDIR="\$TMPDIR_OPT"
export SINGULARITY_TMPDIR="\$TMPDIR_OPT"
export APPTAINER_TMPDIR="\$TMPDIR_OPT"

# Bind common paths; keep it simple and explicit
BIND_REPO="\$REPO_ROOT:/workspace"

if [[ "\$ENGINE" == "docker" ]]; then
  PLATFORM_FLAG=""
  if [[ "\$(uname -m)" == "arm64" ]]; then
    PLATFORM_FLAG="--platform linux/amd64"
  fi

  # Mount repo, work in /workspace
  if [[ "\${#CMD[@]}" -eq 0 ]]; then
    docker run \$PLATFORM_FLAG -it --rm \\
      -v "\$BIND_REPO" \\
      -w /workspace \\
      "\$IMG_DOCKER" \\
      /bin/bash
  else
    docker run \$PLATFORM_FLAG -it --rm \\
      -v "\$BIND_REPO" \\
      -w /workspace \\
      "\$IMG_DOCKER" \\
      "\${CMD[@]}"
  fi
  exit 0
fi

# apptainer/singularity path
SIF="\$SIF_PATH"
if [[ -z "\$SIF" ]]; then
  # Pull on demand from docker registry (cached by engine)
  SIF="docker://\$IMG_DOCKER"
fi

# Engine exec
if [[ "\${#CMD[@]}" -eq 0 ]]; then
  "\$ENGINE" exec --bind "\$BIND_REPO" "\$SIF" /bin/bash
else
  "\$ENGINE" exec --bind "\$BIND_REPO" "\$SIF" "\${CMD[@]}"
fi
EOF

chmod +x "$PREFIX/electra-shell"

echo "Environment setup successful."
echo "Launcher created at: $PREFIX/electra-shell"
echo "Run: $PREFIX/electra-shell"
