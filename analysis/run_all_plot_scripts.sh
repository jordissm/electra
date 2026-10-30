#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMES_SCRIPT_DIR="${SCRIPT_DIR}/scripts/experiment_comparison/hadronization_comparison/times_vs_zh"
TIMES_CONFIG="${TIMES_SCRIPT_DIR}/times_vs_zh_inputs.json"
if [[ ! -f "${TIMES_CONFIG}" ]]; then
  TIMES_CONFIG="${TIMES_SCRIPT_DIR}/times_vs_zh_inputs.example.json"
fi
TIMES_OUTPUT_DIR="${SCRIPT_DIR}/output/plots/experiment_comparison/times_vs_zh"
CLAS_CONFIG="${SCRIPT_DIR}/scripts/CLAS/cross_section_profile_comparison/R_A/RA_vs_zh_inputs.yaml"
CLAS_DATA_ONLY=0
EMC_CONFIG="${SCRIPT_DIR}/scripts/EMC/cross_section_profile_comparison/R_A/RA_vs_zh_inputs.yaml"
EMC_DATA_FILE="${SCRIPT_DIR}/experimental_data/EMC/R_A/Fig4.csv"
EMC_DATA_ONLY=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: bash analysis/run_all_plot_scripts.sh [options]

Run all HERMES model/profile comparisons, CLAS pion Figs. 1-3, EMC R_A, and the
configured experiment time comparison. Continue after failures and exit 1
if any workflow fails. Input files must already exist; no events are generated.

Options:
  --dry-run                 Print workflow commands without generating figures.
  --clas-config FILE        Override the CLAS profile input config.
  --clas-data-only          Plot published CLAS data without simulation inputs.
  --emc-config FILE         Override the EMC profile input config.
  --emc-data-file FILE      Original EMC measurements in the documented CSV format.
  --emc-data-only           Plot EMC measurements without simulation inputs.
  --times-config FILE       Override the time-comparison input config.
  --times-output-dir DIR    Override the time-comparison figure directory.
  -h, --help                Show this help.

The time config defaults to times_vs_zh_inputs.json beside its Python runner,
or the three-experiment example if no local config exists. Set PYTHON to choose
the Python interpreter. Relative option paths resolve from your current directory.
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --clas-data-only) CLAS_DATA_ONLY=1; shift ;;
    --emc-data-only) EMC_DATA_ONLY=1; shift ;;
    --clas-config|--emc-config|--emc-data-file|--times-config|--times-output-dir)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
        echo "[error] $1 requires a path." >&2
        exit 2
      fi
      case "$1" in
        --clas-config) CLAS_CONFIG="$2" ;;
        --emc-config) EMC_CONFIG="$2" ;;
        --emc-data-file) EMC_DATA_FILE="$2" ;;
        --times-config) TIMES_CONFIG="$2" ;;
        --times-output-dir) TIMES_OUTPUT_DIR="$2" ;;
      esac
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

COMPLETED=0
FAILED_WORKFLOWS=()
run_workflow() {
  local label="$1"
  local launcher="$2"
  shift 2
  echo "[run] ${label}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '  '
    printf '%q ' bash "${SCRIPT_DIR}/${launcher}" "$@"
    printf '\n'
  elif bash "${SCRIPT_DIR}/${launcher}" "$@"; then
    COMPLETED=$((COMPLETED + 1))
  else
    FAILED_WORKFLOWS+=("${label}")
    echo "[warn] ${label} failed; continuing with remaining workflows." >&2
  fi
}

run_workflow "HERMES / model comparison / e+d" run_HERMES_model_comparison_plot_scripts_e_d.sh
run_workflow "HERMES / model comparison / R_A" run_HERMES_model_comparison_plot_scripts_R_A.sh
run_workflow "HERMES / cross-section profiles / e+d" run_HERMES_cross_section_profile_comparison_plot_scripts_e_d.sh
run_workflow "HERMES / cross-section profiles / R_A" run_HERMES_cross_section_profile_comparison_plot_scripts_R_A.sh
if [[ "${CLAS_DATA_ONLY}" -eq 1 ]]; then
  run_workflow "CLAS / published R_A data" run_CLAS_cross_section_profile_comparison_plot_scripts_R_A.sh
else
  run_workflow "CLAS / cross-section profiles / R_A" run_CLAS_cross_section_profile_comparison_plot_scripts_R_A.sh \
    --config "${CLAS_CONFIG}"
fi
if [[ "${EMC_DATA_ONLY}" -eq 1 ]]; then
  run_workflow "EMC / published R_A data" run_EMC_cross_section_profile_comparison_plot_scripts_R_A.sh \
    --data-file "${EMC_DATA_FILE}"
else
  run_workflow "EMC / cross-section profiles / R_A" run_EMC_cross_section_profile_comparison_plot_scripts_R_A.sh \
    --config "${EMC_CONFIG}" --data-file "${EMC_DATA_FILE}"
fi
run_workflow "Experiment comparison / hadronization times" run_hadronization_comparison_times_vs_zh.sh \
  --config "${TIMES_CONFIG}" --output-dir "${TIMES_OUTPUT_DIR}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry run complete; no figures generated."
elif [[ ${#FAILED_WORKFLOWS[@]} -gt 0 ]]; then
  echo "${COMPLETED} workflow(s) completed; ${#FAILED_WORKFLOWS[@]} failed:" >&2
  printf '  %s\n' "${FAILED_WORKFLOWS[@]}" >&2
  exit 1
else
  echo "All ${COMPLETED} plotting workflows completed."
fi
