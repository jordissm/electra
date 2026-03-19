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

NEVENTS="${NEVENTS:-1}"
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

ARRAY_RANGE="0-$((NEVENTS - 1))"


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

mkdir -p "${LOG_DIR}"

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
            --profiles-index \${RUN_DIR_CONT}/profiles/profiles.jsonl \
            --nevents ${NEVENTS} \
            --nreplicas ${NREPLICAS} \
            --nprofiles ${NPROFILES} \
            --task-mode ${TASK_MODE} \
            --task-id \${SLURM_ARRAY_TASK_ID}
    "
EOF