#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" \
  "${SCRIPT_DIR}/scripts/experiment_comparison/hadronization_comparison/times_vs_zh/run_times_vs_zh.py" "$@"
