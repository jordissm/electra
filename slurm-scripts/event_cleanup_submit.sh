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
# Parse arguments
# -----------------------------
POSITIONAL=()
for arg in "$@"; do
    case $arg in
        *=*)
            key="${arg%%=*}"
            val="${arg#*=}"
            export "$key"="$val"
            ;;
        *)
            POSITIONAL+=("$arg")
            ;;
    esac
done

if (( ${#POSITIONAL[@]} > 3 )); then
    echo "Usage: $0 [RUN_ID] [SUBRUN_LABEL] [MAX_JOBS] [KEY=VALUE ...]" >&2
    echo "   or: $0 RUN_ID=0 SUBRUN_LABEL=ehijing MAX_JOBS=1" >&2
    exit 1
fi

if (( ${#POSITIONAL[@]} >= 1 )); then
    RUN_ID="${POSITIONAL[0]}"
fi

if (( ${#POSITIONAL[@]} >= 2 )); then
    SUBRUN_LABEL="${POSITIONAL[1]}"
fi

if (( ${#POSITIONAL[@]} >= 3 )); then
    MAX_JOBS="${POSITIONAL[2]}"
fi

# -----------------------------
# User-tunable parameters
# -----------------------------
JOB_NAME="${JOB_NAME:-${JOB_NAME_PREFIX:-electra}:cleanup-events}"
ACCOUNT="${ACCOUNT:-qgp}"
PARTITION="${PARTITION:-qgp}"
TIME_LIMIT="${TIME_LIMIT:-${EVENT_CLEANUP_TIME_LIMIT:-${DEFAULT_TIME_LIMIT:-00:30:00}}}"
CPUS_PER_TASK="${CPUS_PER_TASK:-${DEFAULT_CPUS_PER_TASK:-1}}"
MEMORY="${MEMORY:-${EVENT_CLEANUP_MEMORY:-${DEFAULT_MEMORY:-1G}}}"

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
OUTPUT_HOST="${OUTPUT_HOST:-$PROJECT_ROOT/output}"

RUN_ID="${RUN_ID:-0}"
SUBRUN_LABEL="${SUBRUN_LABEL:-ehijing}"
MAX_JOBS="${MAX_JOBS:-1}"

RUN_DIR_HOST="$OUTPUT_HOST/runs/$RUN_ID/$SUBRUN_LABEL"
EVENTS_DIR="$RUN_DIR_HOST/events"
LOG_DIR="${LOG_DIR:-$RUN_DIR_HOST/logs}"

if ! [[ "$RUN_ID" =~ ^[0-9]+$ ]]; then
    echo "Error: RUN_ID must be a non-negative integer, got '$RUN_ID'" >&2
    exit 1
fi

if [[ -z "$SUBRUN_LABEL" ]]; then
    echo "Error: SUBRUN_LABEL must not be empty" >&2
    exit 1
fi

if ! [[ "$MAX_JOBS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: MAX_JOBS must be a positive integer, got '$MAX_JOBS'" >&2
    exit 1
fi

if [[ ! -d "$EVENTS_DIR" ]]; then
    echo "Error: events directory does not exist: $EVENTS_DIR" >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
DIR_LIST="$(mktemp "$LOG_DIR/event_cleanup_dirs.XXXXXX")"
KEEP_DIR_LIST=false

cleanup_dir_list_on_exit() {
    if [[ "$KEEP_DIR_LIST" != "true" ]]; then
        rm -f -- "$DIR_LIST"
    fi
}
trap cleanup_dir_list_on_exit EXIT

if ! \ls -d "$EVENTS_DIR"/* > "$DIR_LIST" 2>/dev/null; then
    echo "Error: no event directories matched: $EVENTS_DIR/*" >&2
    exit 1
fi

while IFS= read -r DIR; do
    if [[ ! -d "$DIR" ]]; then
        echo "Error: matched path is not a directory: $DIR" >&2
        exit 1
    fi
done < "$DIR_LIST"

NUM_DIRS="$(wc -l < "$DIR_LIST" | tr -d '[:space:]')"

if (( NUM_DIRS == 0 )); then
    echo "Error: no event directories matched: $EVENTS_DIR/*" >&2
    exit 1
fi

ARRAY_RANGE="1-${NUM_DIRS}%${MAX_JOBS}"

echo "Preparing to permanently remove event directories:"
echo "  run id       : $RUN_ID"
echo "  subrun label : $SUBRUN_LABEL"
echo "  events dir   : $EVENTS_DIR"
echo "  list file    : $DIR_LIST"
echo "  directories : $NUM_DIRS"
echo "  max jobs     : $MAX_JOBS"
echo
echo "The files in these directories will be removed permanently."
read -r -p "Submit cleanup job? Type 'yes' to continue: " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
    echo "Aborted. Removing temporary list file: $DIR_LIST"
    rm -f -- "$DIR_LIST"
    trap - EXIT
    exit 0
fi

echo "Submitting cleanup array:"
echo "  array range  : $ARRAY_RANGE"

ARRAY_JOB_ID=$(
sbatch --parsable <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${TIME_LIMIT}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem=${MEMORY}
#SBATCH --array=${ARRAY_RANGE}
#SBATCH -o ${LOG_DIR}/cleanup_%A_%a.out
#SBATCH -e ${LOG_DIR}/cleanup_%A_%a.err

set -euo pipefail

LIST="${DIR_LIST}"
DIR=\$(sed -n "\${SLURM_ARRAY_TASK_ID}p" "\$LIST")

if [[ -z "\$DIR" ]]; then
    echo "No directory listed for SLURM_ARRAY_TASK_ID=\${SLURM_ARRAY_TASK_ID}" >&2
    exit 1
fi

echo "[\$(date)] Removing: \$DIR"
rm -rf -- "\$DIR"
echo "[\$(date)] Done: \$DIR"
EOF
)
KEEP_DIR_LIST=true

LIST_CLEANUP_JOB_ID=$(
sbatch --parsable --dependency=afterok:${ARRAY_JOB_ID} <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:list
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t 00:05:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=256M
#SBATCH -o ${LOG_DIR}/cleanup_list_%j.out
#SBATCH -e ${LOG_DIR}/cleanup_list_%j.err

set -euo pipefail

echo "[\$(date)] Removing temporary event-directory list: ${DIR_LIST}"
rm -f -- "${DIR_LIST}"
echo "[\$(date)] Done"
EOF
)

trap - EXIT

echo "Submitted cleanup array job: $ARRAY_JOB_ID"
echo "Submitted list-file cleanup job: $LIST_CLEANUP_JOB_ID"
