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
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd -P)"

# Container image path
IMG="${IMG:-/scratch/$USER/containers/electra.sif}"

# Output directory on host and container
OUTPUT_HOST="${OUTPUT_HOST:-$PROJECT_ROOT/output}"
OUTPUT_CONT="${OUTPUT_CONT:-/workspace/output}"

# Target parameters are resolved by eHIJING from the selected YAML entry.
NUCLEUS="${NUCLEUS:-d}"
NUCLEUS_DATABASE_DEFAULT="$PROJECT_ROOT/input/ehijing/woods_saxon.yaml"
NUCLEUS_DATABASE="${NUCLEUS_DATABASE:-$NUCLEUS_DATABASE_DEFAULT}"
if ! [[ "$NUCLEUS" =~ ^[A-Za-z][A-Za-z0-9]*$ ]]; then
    echo "Error: NUCLEUS must be a database key such as d or C12" >&2; exit 1
fi
if [[ ! -r "$NUCLEUS_DATABASE" ]]; then
    echo "Error: nucleus database is missing or unreadable: $NUCLEUS_DATABASE" >&2; exit 1
fi
NUCLEUS_DATABASE="$(cd "$(dirname "$NUCLEUS_DATABASE")" && pwd -P)/$(basename "$NUCLEUS_DATABASE")"
MED_MODIF_MODE="${MED_MODIF_MODE:-1}" # Generalized Higher Twist; 0 selects Higher Twist.
K="${K:-4.0}"
# Optional runtime mode and overrides of the selected database parameters.
NUCLEAR_ARGS=""
if [[ -n "${NUCLEAR_TARGET:-}" ]]; then
    case "$NUCLEAR_TARGET" in
        on|off) NUCLEAR_ARGS=" --nuclear-target $NUCLEAR_TARGET" ;;
        *) echo "Error: NUCLEAR_TARGET must be on or off" >&2; exit 1 ;;
    esac
fi
for nuclear_parameter in NUCLEON_WIDTH_FM NUCLEAR_RADIUS_FM NUCLEAR_SURFACE_FM; do
    nuclear_value="${!nuclear_parameter:-}"
    if [[ -z "$nuclear_value" ]]; then continue; fi
    if ! [[ "$nuclear_value" =~ ^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$ ]]; then
        echo "Error: $nuclear_parameter must be a nonnegative number" >&2; exit 1
    fi
    case "$nuclear_parameter" in
        NUCLEON_WIDTH_FM) nuclear_flag="--nucleon-width-fm" ;;
        NUCLEAR_RADIUS_FM) nuclear_flag="--nuclear-radius-fm" ;;
        NUCLEAR_SURFACE_FM) nuclear_flag="--nuclear-surface-fm" ;;
    esac
    NUCLEAR_ARGS="$NUCLEAR_ARGS $nuclear_flag $nuclear_value"
done
# Select the settings bundle under input/ehijing/experiments/ (required).
: "${EXPERIMENT:?Set EXPERIMENT to an experiment directory under input/ehijing/experiments/}"
EXPERIMENT_CONFIG_DIR="$PROJECT_ROOT/input/ehijing/experiments/$EXPERIMENT"
CONFIG_PATH="${CONFIG_PATH:-$EXPERIMENT_CONFIG_DIR/hard_process.setting}"
HADRONIZATION_CONFIG_PATH="${HADRONIZATION_CONFIG_PATH:-$EXPERIMENT_CONFIG_DIR/hadronization.setting}"
DIS_CUTS_CONFIG_PATH="${DIS_CUTS_CONFIG_PATH:-$EXPERIMENT_CONFIG_DIR/dis_cuts.setting}"

for config in \
    "$CONFIG_PATH" \
    "$HADRONIZATION_CONFIG_PATH" \
    "$DIS_CUTS_CONFIG_PATH"
do
    if [[ ! -r "$config" ]]; then
        echo "Error: configuration is missing or unreadable: $config" >&2
        exit 1
    fi
done

SEED="${SEED:-12345}"
if ! [[ "$SEED" =~ ^[0-9]+$ ]]; then
    echo "Error: SEED must be an unsigned decimal integer" >&2; exit 1
fi
# Normalize leading zeros and check the uint64 limit without shell arithmetic.
while [[ ${#SEED} -gt 1 && ${SEED:0:1} == 0 ]]; do SEED="${SEED:1}"; done
if [[ ${#SEED} -gt 20 || ( ${#SEED} -eq 20 && "$SEED" > "18446744073709551615" ) ]]; then
    echo "Error: SEED must fit in an unsigned 64-bit integer" >&2; exit 1
fi

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
echo "  nucleus      : $NUCLEUS"
echo "  database     : $NUCLEUS_DATABASE"
echo "  total events : $NEVENTS"
echo "  medium mode  : $MED_MODIF_MODE (0: HT, 1: GHT)"
echo "  chunk size   : $CHUNK_SIZE"
echo "  num chunks   : $NUM_CHUNKS"
echo "  array range  : $ARRAY_RANGE"
echo "Cluster environment:"
echo "  config file  : $SLURM_CONFIG"
echo "  job prefix   : ${JOB_NAME%:ehijing}"
echo "  account      : $ACCOUNT"
echo "  partition    : $PARTITION"
echo "  sim job name : ${JOB_NAME}:simulation"
echo "  sim time     : $TIME_LIMIT"
echo "  sim cpus     : $CPUS_PER_TASK"
echo "  sim memory   : $MEMORY"
echo "  post job name: ${JOB_NAME}:post"
echo "  post time    : $POST_TIME_LIMIT"
echo "  post memory  : $POST_MEMORY"
echo "  project root : $PROJECT_ROOT"
echo "  output host  : $OUTPUT_HOST"
echo "  output cont  : $OUTPUT_CONT"
echo "  image        : $IMG"
echo "  log dir      : $LOG_DIR"

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

NUCLEUS="${NUCLEUS}"
NUCLEUS_DATABASE="${NUCLEUS_DATABASE}"
NUCLEAR_ARGS="${NUCLEAR_ARGS}"
MED_MODIF_MODE="${MED_MODIF_MODE:-1}"
K="${K:-4.0}"
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
    --bind "\${PROJECT_ROOT}:\${PROJECT_ROOT}" \
    --bind "\${OUTPUT_HOST}:\${OUTPUT_CONT}" \
    --bind "\${NUCLEUS_DATABASE}:\${NUCLEUS_DATABASE}:ro" \
    --pwd /workspace \
    "\${IMG}" \
    /usr/local/bin/entrypoint.sh \
    electra ehijing run \
        --seed ${SEED} \
        --nucleus "\${NUCLEUS}" \${NUCLEAR_ARGS} \
        --nucleus-database "\${NUCLEUS_DATABASE}" \
        --medium-modification-mode \${MED_MODIF_MODE} \
        --K "\${K}" \
        --run-path "\${EHIJING_RUN_DIR_CONT}" \
        --tabulation-path "\${TASK_TABLE_PATH}" \
        --hard-process-config "\${CONFIG_PATH}" \
        --hadronization-config "\${HADRONIZATION_CONFIG_PATH}" \
        --dis-cuts-config "\${DIS_CUTS_CONFIG_PATH}" \
        --number-of-events "\${TASK_NEVENTS}" \
        --first-event-id "\${FIRST_EVENT_ID}" \
        --chunk-size "\${CHUNK_SIZE}"

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
