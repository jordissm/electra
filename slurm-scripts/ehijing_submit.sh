#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLURM_CONFIG="${SLURM_CONFIG:-$SCRIPT_DIR/cluster.env}"

if [[ -f "$SLURM_CONFIG" ]]; then
    # shellcheck source=/dev/null
    set +u
    source "$SLURM_CONFIG"
    set -u
fi

# -----------------------------
# Parse key=value arguments
# -----------------------------
for arg in "$@"; do
    case $arg in
        *=*)
            key="${arg%%=*}"
            val="${arg#*=}"
            export "$key"="$val"
            ;;
        *)
            echo "Warning: ignoring argument '$arg' (expected (key=value format)"
            ;;
    esac
done

# -----------------------------
# User-tunable parameters
# -----------------------------
JOB_NAME="${JOB_NAME:-${JOB_NAME_PREFIX:-electra}:ehijing}"
ACCOUNT="${ACCOUNT:-qgp}"
PARTITION="${PARTITION:-qgp}"
TIME_LIMIT="${TIME_LIMIT:-${EHIJING_TIME_LIMIT:-${DEFAULT_TIME_LIMIT:-00:30:00}}}"
POST_TIME_LIMIT="${POST_TIME_LIMIT:-${EHIJING_POST_TIME_LIMIT:-00:30:00}}"
CPUS_PER_TASK="${CPUS_PER_TASK:-${DEFAULT_CPUS_PER_TASK:-1}}"
MEMORY="${MEMORY:-${DEFAULT_MEMORY:-2G}}"
POST_MEMORY="${POST_MEMORY:-${EHIJING_POST_MEMORY:-1G}}"

# Find project root
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# Container image path
IMG="${IMG:-/scratch/$USER/containers/electra.sif}"

# Output directory on host and container
OUTPUT_HOST="${OUTPUT_HOST:-$PROJECT_ROOT/output}"
OUTPUT_CONT="${OUTPUT_CONT:-/workspace/output}"

# Physical parameters for eHIJING
# HERMES
# d:        He4:      Ne:       Kr:       Xe:
#   Z: 1      Z: 2      Z: 10     Z: 36     Z: 54
#   A: 2      A: 4      A: 20     A: 84     A: 131
# CLAS
# d:        C:        Fe:       Pb:
#   Z: 1      Z: 6      Z: 26     Z: 82
#   A: 2      A: 12     A: 56     A: 208
# EIC
# d:        He3:      C:        Ca:       Fe:       Au:
#   Z: 1      Z: 2      Z: 6      Z: 20     Z: 26     Z: 79
#   A: 2      A: 3      A: 12     A: 40     A: 56     A: 197
Z=1 #36
A=2 #84
MED_MODIF_MODE=0
K=4.0
CONFIG_PATH="${CONFIG_PATH:-$PROJECT_ROOT/input/ehijing/hermes.setting}"
HADRONIZATION_CONFIG_PATH="${HADRONIZATION_CONFIG_PATH:-$PROJECT_ROOT/input/ehijing/hadronization.setting}"
DIS_CUTS_CONFIG_PATH="${DIS_CUTS_CONFIG_PATH:-$PROJECT_ROOT/input/ehijing/dis_cuts/hermes.setting}"

NEVENTS="${NEVENTS:-1}"
CHUNK_SIZE="${CHUNK_SIZE:-1000}"
OVERWRITE_RUN="${OVERWRITE_RUN:-false}"

RUNS_DIR_HOST="$OUTPUT_HOST/runs"
RUNS_DIR_CONT="$OUTPUT_CONT/runs"

is_truthy() {
    case "${1,,}" in
        1|true|yes|y|on) return 0 ;;
        *) return 1 ;;
    esac
}

reserve_run_id() {
    local runs_dir="$1"
    local run_id=0

    mkdir -p "$runs_dir"
    while ! mkdir "$runs_dir/$run_id" 2>/dev/null; do
        run_id=$((run_id + 1))
    done

    printf '%s\n' "$run_id"
}

if [[ -n "${RUN_ID:-}" ]]; then
    if ! [[ "$RUN_ID" =~ ^[0-9]+$ ]]; then
        echo "Error: RUN_ID must be a non-negative integer, got '$RUN_ID'" >&2
        exit 1
    fi

    if [[ -e "$RUNS_DIR_HOST/$RUN_ID" ]]; then
        if ! is_truthy "$OVERWRITE_RUN"; then
            echo "Error: eHIJING run '$RUN_ID' already exists at '$RUNS_DIR_HOST/$RUN_ID'." >&2
            echo "       Re-run with OVERWRITE_RUN=true to reuse it explicitly." >&2
            exit 1
        fi
    else
        mkdir -p "$RUNS_DIR_HOST/$RUN_ID"
    fi
else
    RUN_ID="$(reserve_run_id "$RUNS_DIR_HOST")"
fi

EHIJING_RUN_DIR_HOST="$RUNS_DIR_HOST/$RUN_ID/ehijing"
EHIJING_RUN_DIR_CONT="$RUNS_DIR_CONT/$RUN_ID/ehijing"

TABLE_PATH="${TABLE_PATH:-$EHIJING_RUN_DIR_CONT/tables/K}"
LOG_DIR="$EHIJING_RUN_DIR_HOST/logs"

# -----------------------------
# Validate and convert NEVENTS
# -----------------------------
if ! [[ "$NEVENTS" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: NEVENTS must be a positive integer, got '$NEVENTS'" >&2
            exit 1
fi

if ! [[ "$CHUNK_SIZE" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: CHUNK_SIZE must be a positive integer, got '$CHUNK_SIZE'" >&2
    exit 1
fi


# -----------------------------
# Compute number of array tasks
# -----------------------------
NUM_CHUNKS=$(( (NEVENTS + CHUNK_SIZE - 1) / CHUNK_SIZE ))
ARRAY_RANGE="0-$((NUM_CHUNKS - 1))"


mkdir -p "$LOG_DIR"

echo "Submitting eHIJING run:"
echo "  run id       : $RUN_ID"
echo "  run dir      : $EHIJING_RUN_DIR_CONT"
echo "  total events : $NEVENTS"
echo "  chunk size   : $CHUNK_SIZE"
echo "  num chunks   : $NUM_CHUNKS"
echo "  array range  : $ARRAY_RANGE"

# -----------------------------
# Submit the SLURM job
# -----------------------------
ARRAY_JOB_ID=$(
sbatch --parsable <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:simulation
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${TIME_LIMIT}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem=${MEMORY}
#SBATCH --array=${ARRAY_RANGE}
#SBATCH -o ${LOG_DIR}/ehijing_%A_%a.out
#SBATCH -e ${LOG_DIR}/ehijing_%A_%a.err

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT}"
OUTPUT_HOST="${OUTPUT_HOST}"
IMG="${IMG}"
OUTPUT_CONT="${OUTPUT_CONT}"
EHIJING_RUN_DIR_CONT="${EHIJING_RUN_DIR_CONT}"
TABLE_PATH="${TABLE_PATH}"
CONFIG_PATH="${CONFIG_PATH}"
HADRONIZATION_CONFIG_PATH="${HADRONIZATION_CONFIG_PATH}"
DIS_CUTS_CONFIG_PATH="${DIS_CUTS_CONFIG_PATH}"

Z="${Z}"
A="${A}"
MED_MODIF_MODE="${MED_MODIF_MODE}"
K="${K}"
NEVENTS="${NEVENTS}"
CHUNK_SIZE="${CHUNK_SIZE}"

mkdir -p "${LOG_DIR}"

TASK_ID=\${SLURM_ARRAY_TASK_ID}
TASK_TABLE_PATH="\${TABLE_PATH}/\${TASK_ID}"
FIRST_EVENT_ID=\$(( TASK_ID * CHUNK_SIZE ))
REMAINING=\$(( NEVENTS - FIRST_EVENT_ID ))

if (( REMAINING <= 0 )); then
    echo "Nothing to do for task \$TASK_ID"
    exit 0
fi

if (( REMAINING < CHUNK_SIZE )); then
    TASK_NEVENTS=\${REMAINING}
else
    TASK_NEVENTS=\${CHUNK_SIZE}
fi

apptainer exec \
    --cleanenv \
    --bind "\${OUTPUT_HOST}:\${OUTPUT_CONT}" \
    --pwd /workspace \
    "\${IMG}" \
    /usr/local/bin/entrypoint.sh \
    /bin/bash --noprofile --norc -lc "
        set -euo pipefail
        electra ehijing run \
            --Z ${Z} \
            --A ${A} \
            --medium-modification-mode \${MED_MODIF_MODE} \
            --run-path \${EHIJING_RUN_DIR_CONT} \
            --tabulation-path \${TASK_TABLE_PATH} \
            --hard-process-config \${CONFIG_PATH} \
            --hadronization-config \${HADRONIZATION_CONFIG_PATH} \
            --dis-cuts-config \${DIS_CUTS_CONFIG_PATH} \
            --number-of-events \${TASK_NEVENTS} \
            --first-event-id \${FIRST_EVENT_ID} \
            --chunk-size \${CHUNK_SIZE} \
    "
EOF
)

sbatch --dependency=afterok:${ARRAY_JOB_ID} <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:post
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${POST_TIME_LIMIT}
#SBATCH --cpus-per-task=1
#SBATCH --mem=${POST_MEMORY}
#SBATCH -o /dev/null
#SBATCH -e /dev/null

set -euo pipefail

find "${EHIJING_RUN_DIR_HOST}/events" -name "*.meta.json" -print0 \
  | sort -z \
  | xargs -0 cat > "${EHIJING_RUN_DIR_HOST}/DISKinematics.meta.jsonl"

EOF
