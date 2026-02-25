#!/usr/bin/env bash
set -euo pipefail

export SIF_ELECTRA="${SIF_ELECTRA:-$PWD/containers/electra.sif}"
export CAMPAIGN="${CAMPAIGN:-$PWD/runs/campaign_$(date +%F_%H%M%S)}"

# Standard locations inside the campaign folder
export INPUT_DIR="$CAMPAIGN/inputs"
export SMASH_DIR="$CAMPAIGN/smash"
export RIVET_DIR="$CAMPAIGN/rivet"
export LOG_DIR="$CAMPAIGN/logs"
export META_DIR="$CAMPAIGN/meta"
