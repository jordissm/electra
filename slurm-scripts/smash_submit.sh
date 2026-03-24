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
JOB_NAME="${JOB_NAME:-electra:smash}"
ACCOUNT="${ACCOUNT:-qgp}"
PARTITION="${PARTITION:-qgp}"
TIME_LIMIT="${TIME_LIMIT:-00:30:00}"
CPUS_PER_TASK="${CPUS_PER_TASK:-1}"
MEMORY="${MEMORY:-2G}"

PROJECT_ROOT="${PROJECT_ROOT:-/projects/illinois/eng/physics/jnorhos/jordi/electra}"
RUN_DIR_HOST="${RUN_DIR_HOST:-$PROJECT_ROOT/output}"
IMG="${IMG:-/scratch/$USER/containers/electra.sif}"

RUN_DIR_CONT="${RUN_DIR_CONT:-/workspace/output}"
CONFIG_FILE="${CONFIG_FILE:-/projects/illinois/eng/physics/jnorhos/jordi/electra/input/smash/config_files/config.yaml}"
PROFILES="${PROFILES:-/projects/illinois/eng/physics/jnorhos/jordi/electra/input/smash/profiles/profiles.jsonl}"

NEVENTS="${NEVENTS:-1000}"
CHUNK_SIZE="${CHUNK_SIZE:-1000}"
NREPLICAS="${NREPLICAS:-1000}"
NPROFILES="${NPROFILES:-1}"
TASK_MODE="${TASK_MODE:-one}"

LOG_DIR="$RUN_DIR_HOST/runs/smash/logs"

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

NCHUNKS=$(( (NEVENTS + CHUNK_SIZE - 1) / CHUNK_SIZE ))
ARRAY_RANGE="0-$((NCHUNKS - 1))"


mkdir -p "$LOG_DIR"

# -----------------------------
# Submit the SLURM job
# -----------------------------
sbatch <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:simulation
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${TIME_LIMIT}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem=${MEMORY}
#SBATCH --array=${ARRAY_RANGE}
#SBATCH -o ${LOG_DIR}/smash_%A_%a.out
#SBATCH -e ${LOG_DIR}/smash_%A_%a.err

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT}"
RUN_DIR_HOST="${RUN_DIR_HOST}"
IMG="${IMG}"
RUN_DIR_CONT="${RUN_DIR_CONT}"
CONFIG_FILE="${CONFIG_FILE}"
PROFILES="${PROFILES}"
LOG_DIR="${LOG_DIR}"

NEVENTS="${NEVENTS}"
CHUNK_SIZE="${CHUNK_SIZE}"
NREPLICAS="${NREPLICAS}"
NPROFILES="${NPROFILES}"
TASK_MODE="${TASK_MODE}"

mkdir -p "\${LOG_DIR}"

FIRST_EVENT_ID=\$((SLURM_ARRAY_TASK_ID * CHUNK_SIZE))
REMAINING=\$((NEVENTS - FIRST_EVENT_ID))

if (( REMAINING <= 0 )); then
    exit 0
fi

if (( REMAINING < CHUNK_SIZE )); then
    NTHIS=\${REMAINING}
else
    NTHIS=\${CHUNK_SIZE}
fi

NTASKS=\$((NTHIS * NPROFILES))

echo "SLURM_ARRAY_TASK_ID=\${SLURM_ARRAY_TASK_ID}"
echo "FIRST_EVENT_ID=\${FIRST_EVENT_ID}"
echo "NTHIS=\${NTHIS}"
echo "NPROFILES=\${NPROFILES}"
echo "NTASKS=\${NTASKS}"

for TASK_ID in \$(seq 0 \$((NTASKS - 1))); do
    echo "Running TASK_ID=\${TASK_ID} for chunk starting at FIRST_EVENT_ID=\${FIRST_EVENT_ID}"

    apptainer exec \
        --cleanenv \
        --bind "\${RUN_DIR_HOST}:\${RUN_DIR_CONT}" \
        --pwd /workspace \
        "\${IMG}" \
        /usr/local/bin/entrypoint.sh \
        /bin/bash --noprofile --norc -lc "
            set -euo pipefail
            electra smash run \
                --run-dir \${RUN_DIR_CONT}/runs \
                --config-file \${CONFIG_FILE} \
                --profiles-index \${PROFILES} \
                --nevents \${NTHIS} \
                --nreplicas \${NREPLICAS} \
                --nprofiles \${NPROFILES} \
                --task-mode \${TASK_MODE} \
                --first-event-id \${FIRST_EVENT_ID} \
                --task-id \${TASK_ID}
        "
done
EOF