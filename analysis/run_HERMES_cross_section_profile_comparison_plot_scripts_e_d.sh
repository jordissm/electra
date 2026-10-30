#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLOT_SCRIPT_DIR="${SCRIPT_DIR}/scripts/HERMES/cross_section_profile_comparison/e_d"
EXPERIMENTAL_DATA_DIR="${SCRIPT_DIR}/experimental_data"
DATA_DIR="${SCRIPT_DIR}/output/data/HERMES/cross_section_profile_comparison/R_A/d"
OUTPUT_DIR="${SCRIPT_DIR}/output/plots/HERMES/cross_section_profile_comparison/R_A"
PYTHON="${PYTHON:-python3}"
FAILURES=0
ZH_SCALING_FACTORS=(100 20 5 1)

echo "Running cross-section profile comparison plot scripts for HERMES e+d data..."

run_plot() {
  local script_name="$1"
  local observable_dir="$2"
  local output_filename="$3"
  shift 3

  local profile_files=()
  local profile
  for profile in "${DATA_DIR}"/profile_*.yoda; do
    if [[ -s "${profile}" ]]; then
      profile_files+=("${profile}")
    else
      echo "[warn] empty profile file: ${profile}; skipping." >&2
    fi
  done
  if ((${#profile_files[@]} == 0)); then
    echo "[warn] no nonempty profile_*.yoda files found in ${DATA_DIR}; plotting available experimental data for ${script_name}." >&2
  fi

  if ! "${PYTHON}" "${PLOT_SCRIPT_DIR}/${script_name}" \
    --profile-files "${profile_files[@]}" \
    --hepdata-dir "${EXPERIMENTAL_DATA_DIR}/HERMES/R_A/d/${observable_dir}" \
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
