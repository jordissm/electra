#!/usr/bin/env bash
#SBATCH -J electra
#SBATCH -t 02:00:00
#SBATCH -c 1
#SBATCH --mem=2G
#SBATCH -o %x_%A_%a.out
#SBATCH -e %x_%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

: "${ELECTRA_RUN_DIR:?}"
: "${ELECTRA_STAGE:?}"

TASK_ID="${SLURM_ARRAY_TASK_ID}"

# All logic stays inside electra:
./electra worker \
  --run-dir "${ELECTRA_RUN_DIR}" \
  --stage "${ELECTRA_STAGE}" \
  --task-id "${TASK_ID}"
