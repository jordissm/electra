#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILURES=0
for comparison in model_comparison cross_section_profile_comparison; do
  if ! bash "${SCRIPT_DIR}/run_CLAS_${comparison}_plot_scripts_R_A.sh" \
    --config "${SCRIPT_DIR}/scripts/CLAS/${comparison}/R_A/RA_vs_zh_inputs.yaml" "$@"; then
    echo "[warn] ${comparison} failed; continuing." >&2
    FAILURES=$((FAILURES + 1))
  fi
done
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "${FAILURES} CLAS plotting workflow(s) failed." >&2
  exit 1
fi
