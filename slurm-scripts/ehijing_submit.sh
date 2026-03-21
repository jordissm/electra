#!/usr/bin/env bash
set -euo pipefail

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
JOB_NAME="${JOB_NAME:-electra:ehijing}"
ACCOUNT="${ACCOUNT:-qgp}"
PARTITION="${PARTITION:-qgp}"
TIME_LIMIT="${TIME_LIMIT:-00:30:00}"
CPUS_PER_TASK="${CPUS_PER_TASK:-1}"
MEMORY="${MEMORY:-2G}"

PROJECT_ROOT="${PROJECT_ROOT:-/projects/illinois/eng/physics/jnorhos/jordi/electra}"
RUN_DIR_HOST="${RUN_DIR_HOST:-$PROJECT_ROOT/output}"
IMG="${IMG:-/scratch/$USER/containers/electra.sif}"

RUN_DIR_CONT="${RUN_DIR_CONT:-/workspace/output}"

Z=1
A=2
MODE=0
K=4.0
TABLE_PATH="${TABLE_PATH:-$RUN_DIR_CONT/runs/ehijing/tables/K}"
CONFIG_PATH="${CONFIG_PATH:-/workspace/input/ehijing/hermes.setting}"

NEVENTS="${NEVENTS:-1}"
CHUNK_SIZE="${CHUNK_SIZE:-1000}"


LOG_DIR="$RUN_DIR_HOST/runs/ehijing/logs"

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
RUN_DIR_HOST="${RUN_DIR_HOST}"
IMG="${IMG}"
RUN_DIR_CONT="${RUN_DIR_CONT}"
TABLE_PATH="${TABLE_PATH}"
CONFIG_PATH="${CONFIG_PATH}"

mkdir -p "${LOG_DIR}"

TASK_ID=\${SLURM_ARRAY_TASK_ID}
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
    --bind "\${RUN_DIR_HOST}:\${RUN_DIR_CONT}" \
    --pwd /workspace \
    "\${IMG}" \
    /usr/local/bin/entrypoint.sh \
    /bin/bash --noprofile --norc -lc "
        set -euo pipefail
        electra ehijing run \
            --Z ${Z} \
            --A ${A} \
            --mode ${MODE} \
            --run-dir \${RUN_DIR_CONT}/runs \
            --table-path \${TABLE_PATH} \
            --config-file \${CONFIG_PATH} \
            --nevents \${TASK_NEVENTS} \
            --first-event-id \${FIRST_EVENT_ID}
    "
EOF
)

# sbatch --dependency=afterok:${ARRAY_JOB_ID} <<EOF
# #!/bin/bash
# #SBATCH -J ${JOB_NAME}:post
# #SBATCH -A ${ACCOUNT}
# #SBATCH -p ${PARTITION}
# #SBATCH -t 00:10:00
# #SBATCH --cpus-per-task=1
# #SBATCH --mem=1G
# #SBATCH -o /dev/null
# #SBATCH -e /dev/null

# set -euo pipefail

# cat ${RUN_DIR_HOST}/runs/ehijing/events/*.meta.json > ${RUN_DIR_HOST}/runs/ehijing/events/run.meta.json

# EOF