#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running all HERMES plot scripts..."
FAILURES=0

run_script() {
  local script_name="$1"

  if ! bash "${SCRIPT_DIR}/${script_name}"; then
    echo "[warn] ${script_name} failed; continuing." >&2
    FAILURES=$((FAILURES + 1))
  fi
}

run_script "run_HERMES_model_comparison_plot_scripts_e_d.sh"
run_script "run_HERMES_model_comparison_plot_scripts_R_A.sh"
run_script "run_HERMES_cross_section_profile_comparison_plot_scripts_e_d.sh"
run_script "run_HERMES_cross_section_profile_comparison_plot_scripts_R_A.sh"

echo "Finished all HERMES plot scripts."
if [[ "$FAILURES" -gt 0 ]]; then
  echo "${FAILURES} plotting workflow(s) failed; inspect the errors above." >&2
  exit 1
fi
