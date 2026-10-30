#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
PLOT_SCRIPT_DIR="${SCRIPT_DIR}/scripts/CLAS/model_comparison/R_A"
FAILURES=0
for script in plot_RA_vs_zh.py plot_RA_vs_zh_binned_Q2_nu.py; do
  if ! "${PYTHON}" "${PLOT_SCRIPT_DIR}/${script}" "$@"; then
    echo "[warn] ${script} failed; continuing." >&2
    FAILURES=$((FAILURES + 1))
  fi
done
if [[ "${FAILURES}" -gt 0 ]]; then
  echo "${FAILURES} CLAS plot script(s) failed." >&2
  exit 1
fi
