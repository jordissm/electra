#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" \
  "${SCRIPT_DIR}/scripts/EMC/cross_section_profile_comparison/R_A/plot_RA_vs_zh.py" "$@"
