#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"

mkdir -p "$INPUT_DIR" "$SMASH_DIR" "$RIVET_DIR" "$LOG_DIR" "$META_DIR"

echo "CAMPAIGN=$CAMPAIGN"
echo "Created:"
echo "  $INPUT_DIR"
echo "  $SMASH_DIR"
echo "  $RIVET_DIR"
echo "  $LOG_DIR"
echo "  $META_DIR"

