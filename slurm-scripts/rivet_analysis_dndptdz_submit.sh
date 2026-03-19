#!/usr/bin/env bash
set -euo pipefail

# run_rivet_dndptdz_per_profile.sh
#
# Run the Rivet analysis EHIJING_SMASH_DNDPtDZ once per SMASH "profile_p_XXXXXX",
# WITHOUT merging across profiles, and write one YODA per profile.
#
# Tailored for Rivet v3.1.7 (no --analysis-opts), so we pass configuration via env vars:
#   RIVET_METAFILE, RIVET_FRAME, RIVET_PT_MIN, RIVET_PT_MAX, RIVET_PT_NBINS
#
# Usage:
#   ./run_rivet_dndptdz_per_profile.sh \
#     /path/to/run/smash \
#     /path/to/run.meta.json \
#     BREIT \
#     /path/to/RivetEHIJING_SMASH_2026_DNDPtDZ.so \
#     [PT_MIN] [PT_MAX] [PT_NBINS]
#
# Examples:
#   # Default pT axis (0..2 GeV, 40 bins) as in the C++ analysis defaults:
#   ./run_rivet_dndptdz_per_profile.sh run/smash run/ehijing/events/run.meta.json BREIT rivet/RivetEHIJING_SMASH_2026_DNDPtDZ.so
#
#   # Custom pT axis: 0..5 GeV, 100 bins
#   ./run_rivet_dndptdz_per_profile.sh run/smash run/ehijing/events/run.meta.json BREIT rivet/RivetEHIJING_SMASH_2026_DNDPtDZ.so 0.0 5.0 100
#
# Notes:
# - If your HepMC files have inconsistent "beam" particles between files, add --ignore-beams
#   (this ignores beam *consistency checks*, it does NOT drop particles from the event record).

SMASH_DIR="${1:?Need SMASH dir (e.g. run/smash)}"
META_JSON="${2:?Need meta json path (e.g. run/ehijing/events/run.meta.json)}"
FRAME="${3:-BREIT}"
RIVET_SO="${4:?Need Rivet analysis .so path}"
PT_MIN="${5:-}"
PT_MAX="${6:-}"
PT_NBINS="${7:-}"

ANA="EHIJING_SMASH_DNDPtDZ"

# Resolve rivet binary (prefer PATH, else fall back to common install prefix)
RIVET_BIN="$(command -v rivet || true)"
if [[ -z "${RIVET_BIN}" ]]; then
  if [[ -x "/opt/electra/Rivet_install/bin/rivet" ]]; then
    RIVET_BIN="/opt/electra/Rivet_install/bin/rivet"
  else
    echo "ERROR: rivet not found in PATH and /opt/electra/Rivet_install/bin/rivet not executable" >&2
    exit 1
  fi
fi

if [[ ! -d "$SMASH_DIR" ]]; then
  echo "ERROR: SMASH dir not found: $SMASH_DIR" >&2
  exit 1
fi
if [[ ! -f "$META_JSON" ]]; then
  echo "ERROR: meta json not found: $META_JSON" >&2
  exit 1
fi
if [[ ! -f "$RIVET_SO" ]]; then
  echo "ERROR: Rivet .so not found: $RIVET_SO" >&2
  exit 1
fi

# Basic frame validation
case "$FRAME" in
  LAB|TRF|BREIT) ;;
  *)
    echo "ERROR: FRAME must be LAB, TRF, or BREIT (got '$FRAME')" >&2
    exit 1
    ;;
esac

# Numeric validators
is_number() {
  [[ "${1:-}" =~ ^[-+]?[0-9]*([.][0-9]+)?([eE][-+]?[0-9]+)?$ ]]
}
is_int() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

USE_PT_AXIS=0
if [[ -n "$PT_MIN" || -n "$PT_MAX" || -n "$PT_NBINS" ]]; then
  # Must provide all three
  if [[ -z "$PT_MIN" || -z "$PT_MAX" || -z "$PT_NBINS" ]]; then
    echo "ERROR: Provide PT_MIN PT_MAX PT_NBINS together, or provide none to use defaults." >&2
    exit 1
  fi
  if ! is_number "$PT_MIN" || ! is_number "$PT_MAX"; then
    echo "ERROR: PT_MIN/PT_MAX must be numbers (got '$PT_MIN' '$PT_MAX')" >&2
    exit 1
  fi
  if ! is_int "$PT_NBINS"; then
    echo "ERROR: PT_NBINS must be a positive integer (got '$PT_NBINS')" >&2
    exit 1
  fi
  # Compare as floats using awk (portable): require PT_MAX > PT_MIN
  if awk "BEGIN{exit !($PT_MAX <= $PT_MIN)}"; then
    echo "ERROR: PT_MAX <= PT_MIN ($PT_MAX <= $PT_MIN)" >&2
    exit 1
  fi
  if [[ "$PT_NBINS" -le 0 ]]; then
    echo "ERROR: PT_NBINS must be > 0 (got '$PT_NBINS')" >&2
    exit 1
  fi
  USE_PT_AXIS=1
fi

# Output directory
OUTDIR="/workspace/output/runs/rivet/rivet_out_${ANA}_${FRAME}"
if [[ $USE_PT_AXIS -eq 1 ]]; then
  PT_TAG="pt_${PT_MIN}_to_${PT_MAX}_nb${PT_NBINS}"
  PT_TAG="${PT_TAG//./p}"
  PT_TAG="${PT_TAG//-/m}"
  OUTDIR="${OUTDIR}_${PT_TAG}"
fi
mkdir -p "$OUTDIR"

# Find all HepMC files
mapfile -t FILES < <(find "$SMASH_DIR" -type f -name "SMASH_HepMC_particles.asciiv3" | sort)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERROR: No SMASH_HepMC_particles.asciiv3 found under $SMASH_DIR" >&2
  exit 1
fi

# Extract distinct profile names (profile_p_XXXXXX)
PROFILES=$(printf "%s\n" "${FILES[@]}" \
  | sed -n 's|^.*/\(profile_p_[0-9]\{6\}\)/SMASH_HepMC_particles\.asciiv3$|\1|p' \
  | sort -u)

echo "Rivet bin: ${RIVET_BIN}"
echo "Analysis:  ${ANA}"
echo "Frame:     ${FRAME}"
echo "Meta file: ${META_JSON}"
echo "Plugin:    ${RIVET_SO}"
if [[ $USE_PT_AXIS -eq 1 ]]; then
  echo "pT axis:   ${PT_NBINS} bins in [${PT_MIN}, ${PT_MAX}] GeV"
else
  echo "pT axis:   (defaults from analysis: PT_MIN=0, PT_MAX=2, PT_NBINS=40)"
fi
echo "Outdir:    ${OUTDIR}"
echo
echo "Found profiles:"
echo "$PROFILES" | sed 's|^|  - |'

ANA_PATH="$(dirname "$RIVET_SO")"

# Run once per profile so we do NOT merge across profiles
while IFS= read -r PROFILE_NAME; do
  [[ -z "$PROFILE_NAME" ]] && continue

  YODA_OUT="${OUTDIR}/${PROFILE_NAME}.yoda"

  # Collect the matching profile file across all evt_XXXXXX (same profile id)
  mapfile -t PF_FILES < <(find "$SMASH_DIR" -type f -path "*/${PROFILE_NAME}/SMASH_HepMC_particles.asciiv3" | sort)

  if [[ ${#PF_FILES[@]} -eq 0 ]]; then
    echo "WARNING: No files found for ${PROFILE_NAME}, skipping." >&2
    continue
  fi

  echo
  echo "=== Running Rivet for ${PROFILE_NAME} ==="
  echo "Nfiles:  ${#PF_FILES[@]}"
  echo "Output:  ${YODA_OUT}"
  echo

  # Build env for this run
  export RIVET_METAFILE="$META_JSON"
  export RIVET_FRAME="$FRAME"
  export RIVET_PHOTONGOING=1
  export RIVET_VETO_SPECTATORS=1
  export RIVET_SPECTATOR_PMAX=0.001

  if [[ $USE_PT_AXIS -eq 1 ]]; then
    export RIVET_PT_MIN="$PT_MIN"
    export RIVET_PT_MAX="$PT_MAX"
    export RIVET_PT_NBINS="$PT_NBINS"
  else
    unset RIVET_PT_MIN || true
    unset RIVET_PT_MAX || true
    unset RIVET_PT_NBINS || true
  fi

  # Print the exact command (nice for logs)
  echo "RIVET_METAFILE=\"${RIVET_METAFILE}\" \\"
  echo "RIVET_FRAME=\"${RIVET_FRAME}\" \\"
  echo "RIVET_PHOTONGOING=\"${RIVET_PHOTONGOING}\" \\"
  echo "RIVET_VETO_SPECTATORS=\"${RIVET_VETO_SPECTATORS}\" \\"
  echo "RIVET_SPECTATOR_PMAX=\"${RIVET_SPECTATOR_PMAX}\" \\"
  if [[ $USE_PT_AXIS -eq 1 ]]; then
    echo "RIVET_PT_MIN=\"${RIVET_PT_MIN}\" \\"
    echo "RIVET_PT_MAX=\"${RIVET_PT_MAX}\" \\"
    echo "RIVET_PT_NBINS=\"${RIVET_PT_NBINS}\" \\"
  fi
  echo "\"${RIVET_BIN}\" --ignore-beams -a \"${ANA}\" --pwd --analysis-path \"${ANA_PATH}\" -o \"${YODA_OUT}\" \\"
  echo "  <${#PF_FILES[@]} input files>"
  echo

  "${RIVET_BIN}" \
    -a "${ANA}" \
    --pwd \
    --analysis-path "${ANA_PATH}" \
    --ignore-beams \
    -o "${YODA_OUT}" \
    "${PF_FILES[@]}"

done <<< "$PROFILES"

echo
echo "Done. Outputs in: ${OUTDIR}"