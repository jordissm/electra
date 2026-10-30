#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLOT_SCRIPT_DIR="${SCRIPT_DIR}/scripts/HERMES/model_comparison/R_A"
EXPERIMENTAL_DATA_DIR="${SCRIPT_DIR}/experimental_data"
OUTPUT_DIR="${SCRIPT_DIR}/output/HERMES/model_comparison/R_A"
PYTHON="${PYTHON:-python3}"
FAILURES=0

echo "Running model-comparison R_A plot scripts for HERMES data..."

run_plot() {
  local script_name="$1"
  local config_filename="$2"
  local output_filename="$3"
  shift 3

  if ! "${PYTHON}" "${PLOT_SCRIPT_DIR}/${script_name}" \
    --config "${PLOT_SCRIPT_DIR}/${config_filename}" \
    --data-dir "${EXPERIMENTAL_DATA_DIR}/HERMES/R_A" \
    --output-dir "${OUTPUT_DIR}" \
    --output-filename "${output_filename}" \
    "$@"; then
    echo "[warn] ${script_name} failed; continuing." >&2
    FAILURES=$((FAILURES + 1))
  fi
}

run_plot "plot_RA_vs_zh.py" "RA_vs_zh_inputs.yaml" "RA_vs_zh.pdf"

if ! "${PYTHON}" "${SCRIPT_DIR}/scripts/HERMES/plot_hermes_fig2.py" \
  --comparison model --config "${PLOT_SCRIPT_DIR}/RA_vs_zh_inputs.yaml" \
  --data-dir "${EXPERIMENTAL_DATA_DIR}/HERMES/R_A" \
  --output-dir "${OUTPUT_DIR}" --output-filename RA_fig2.pdf; then
  echo "[warn] plot_hermes_fig2.py failed." >&2
  FAILURES=$((FAILURES + 1))
fi

if [[ "${FAILURES}" -gt 0 ]]; then
  echo "${FAILURES} plot(s) failed in ${BASH_SOURCE[0]##*/}." >&2
  exit 1
fi
