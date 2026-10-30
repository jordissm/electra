#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLOT_SCRIPT_DIR="${SCRIPT_DIR}/scripts/HERMES/model_comparison/e_d"
EXPERIMENTAL_DATA_DIR="${SCRIPT_DIR}/experimental_data"
OUTPUT_DIR="${SCRIPT_DIR}/output/HERMES/model_comparison/e_d"
PYTHON="${PYTHON:-python3}"
FAILURES=0
ZH_SCALING_FACTORS=(100 20 5 1)

echo "Running plot scripts for HERMES e+d data..."

run_plot() {
  local script_name="$1"
  local observable_dir="$2"
  local output_filename="$3"
  shift 3

  if ! "${PYTHON}" "${PLOT_SCRIPT_DIR}/${script_name}" \
    --ehijing-decays "${OUTPUT_DIR}/ehijing-decays.yoda" \
    --smash-decays-only "${OUTPUT_DIR}/ehijing-smash-decays-only.yoda" \
    --smash-decays-collisions "${OUTPUT_DIR}/ehijing-smash-decays-collisions.yoda" \
    --hepdata-dir "${EXPERIMENTAL_DATA_DIR}/HERMES/e_d/${observable_dir}" \
    --output-dir "${OUTPUT_DIR}" \
    --output-filename "${output_filename}" \
    "$@"; then
    echo "[warn] ${script_name} failed for ${observable_dir}; continuing." >&2
    FAILURES=$((FAILURES + 1))
  fi
}

run_plot "plot_dndz.py" "DNDZ" "dndz.pdf"
run_plot "plot_dndptdz.py" "DNDPTDZ" "dndptdz.pdf" --zh-scales "${ZH_SCALING_FACTORS[@]}"
run_plot "plot_dndQ2dz.py" "DNDQ2DZ" "dndQ2dz.pdf" --zh-scales "${ZH_SCALING_FACTORS[@]}"
run_plot "plot_dndxbdz.py" "DNDXBDZ" "dndxbdz.pdf" --zh-scales "${ZH_SCALING_FACTORS[@]}"

if [[ "${FAILURES}" -gt 0 ]]; then
  echo "${FAILURES} plot(s) failed in ${BASH_SOURCE[0]##*/}." >&2
  exit 1
fi
