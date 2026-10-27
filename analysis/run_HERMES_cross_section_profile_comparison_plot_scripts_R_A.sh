#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLOT_SCRIPT_DIR="${SCRIPT_DIR}/scripts/cross_section_profile_comparison/R_A"
EXPERIMENTAL_DATA_DIR="${SCRIPT_DIR}/experimental_data"
OUTPUT_DIR="${SCRIPT_DIR}/output/HERMES/cross_section_profile_comparison/R_A"
PYTHON="${PYTHON:-python3}"

echo "Running cross-section profile comparison R_A plot scripts for HERMES data..."

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
  fi
}

run_plot "plot_RA_vs_zh.py" "RA_vs_zh_inputs.yaml" "RA_vs_zh.pdf"
run_plot "plot_HP2026_poster.py" "RA_vs_zh_inputs.yaml" "HP2026_poster.pdf"

"${PYTHON}" "${SCRIPT_DIR}/scripts/plot_hermes_fig2.py" \
  --comparison cross-section-profile --config "${PLOT_SCRIPT_DIR}/RA_vs_zh_inputs.yaml" \
  --data-dir "${EXPERIMENTAL_DATA_DIR}/HERMES/R_A" \
  --output-dir "${OUTPUT_DIR}" --output-filename RA_fig2.pdf
