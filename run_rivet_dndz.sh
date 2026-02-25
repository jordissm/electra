#!/usr/bin/env bash
set -euo pipefail

# run_rivet_dndz_per_profile_yodamerge.sh
#
# Run Rivet per HepMC file (so the plugin can infer evt_XXXXXX from the file path),
# producing one YODA per evt for each profile, then merge them into one YODA per profile
# using yoda-merge (no Rivet plugin loading / no rerun finalize).
#
# Usage:
#   bash run_rivet_dndz_per_profile_yodamerge.sh \
#     run/smash/ \
#     run/ehijing/events/run.meta.json \
#     BREIT \
#     rivet/RivetEHIJING_SMASH_2026_DNDZ.so \
#     [PT2_MIN] [PT2_MAX]
#
# Example:
#   bash run_rivet_dndz_per_profile_yodamerge.sh run/smash run/ehijing/events/run.meta.json BREIT rivet/RivetEHIJING_SMASH_2026_DNDZ.so
#   bash run_rivet_dndz_per_profile_yodamerge.sh run/smash run/ehijing/events/run.meta.json BREIT rivet/RivetEHIJING_SMASH_2026_DNDZ.so 0.0 1.0

SMASH_DIR="${1:?Need SMASH dir (e.g. run/smash)}"
META_JSON="${2:?Need meta json path (e.g. run/ehijing/events/run.meta.json)}"
FRAME="${3:-TRF}"
RIVET_SO="${4:?Need Rivet analysis .so path}"
PT2_MIN="${5:-}"
PT2_MAX="${6:-}"

# IMPORTANT: this must match the analysis name registered by your plugin
# If your plugin class is EHIJING_SMASH_DNDZ, keep it as that.
ANA="EHIJING_SMASH_2026_DNDZ"

HEPMC_BASENAME="SMASH_HepMC_collisions_fixed.asciiv3"

is_number() {
  [[ "${1:-}" =~ ^[-+]?[0-9]*([.][0-9]+)?([eE][-+]?[0-9]+)?$ ]]
}

# -------------------------
# Resolve binaries
# -------------------------

RIVET_BIN="$(command -v rivet || true)"
if [[ -z "${RIVET_BIN}" ]]; then
  if [[ -x "/SMASH/Rivet_install/bin/rivet" ]]; then
    RIVET_BIN="/SMASH/Rivet_install/bin/rivet"
  else
    echo "ERROR: rivet not found in PATH and /SMASH/Rivet_install/bin/rivet not executable" >&2
    exit 1
  fi
fi

# YODA merge tool can be called yoda-merge or yodamerge depending on install
YODA_MERGE="$(command -v yoda-merge || true)"
if [[ -z "${YODA_MERGE}" ]]; then
  YODA_MERGE="$(command -v yodamerge || true)"
fi
if [[ -z "${YODA_MERGE}" ]]; then
  if [[ -x "/SMASH/Rivet_install/bin/yoda-merge" ]]; then
    YODA_MERGE="/SMASH/Rivet_install/bin/yoda-merge"
  elif [[ -x "/SMASH/Rivet_install/bin/yodamerge" ]]; then
    YODA_MERGE="/SMASH/Rivet_install/bin/yodamerge"
  else
    echo "ERROR: yoda-merge (or yodamerge) not found in PATH or /SMASH/Rivet_install/bin" >&2
    exit 1
  fi
fi

# -------------------------
# Input validation
# -------------------------

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

case "$FRAME" in
  LAB|TRF|BREIT) ;;
  *)
    echo "ERROR: FRAME must be LAB, TRF, or BREIT (got '$FRAME')" >&2
    exit 1
    ;;
esac

USE_PT2=0
if [[ -n "$PT2_MIN" || -n "$PT2_MAX" ]]; then
  if [[ -z "$PT2_MIN" || -z "$PT2_MAX" ]]; then
    echo "ERROR: Provide both PT2_MIN and PT2_MAX, or neither." >&2
    exit 1
  fi
  if ! is_number "$PT2_MIN" || ! is_number "$PT2_MAX"; then
    echo "ERROR: PT2_MIN/PT2_MAX must be numbers (got '$PT2_MIN' '$PT2_MAX')" >&2
    exit 1
  fi
  if awk "BEGIN{exit !($PT2_MAX < $PT2_MIN)}"; then
    echo "ERROR: PT2_MAX < PT2_MIN ($PT2_MAX < $PT2_MIN)" >&2
    exit 1
  fi
  USE_PT2=1
fi

# -------------------------
# Output dir naming (cosmetic)
# -------------------------

OUTDIR="rivet_out_EHIJING_SMASH_2026_DNDZ_${FRAME}"
if [[ $USE_PT2 -eq 1 ]]; then
  PT2_TAG="pt2_${PT2_MIN}_to_${PT2_MAX}"
  PT2_TAG="${PT2_TAG//./p}"
  PT2_TAG="${PT2_TAG//-/m}"
  OUTDIR="${OUTDIR}_${PT2_TAG}"
fi
mkdir -p "$OUTDIR"

# -------------------------
# Discover profiles
# -------------------------

mapfile -t FILES < <(find "$SMASH_DIR" -type f -name "SMASH_HepMC_particles.asciiv3" | sort)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERROR: No SMASH_HepMC_particles.asciiv3 found under $SMASH_DIR" >&2
  exit 1
fi

PROFILES=$(printf "%s\n" "${FILES[@]}" \
  | sed -n 's|^.*/\(profile_p_[0-9]\{6\}\)/SMASH_HepMC_particles\.asciiv3$|\1|p' \
  | sort -u)

if [[ -z "${PROFILES}" ]]; then
  echo "ERROR: Could not infer any profiles under $SMASH_DIR" >&2
  exit 1
fi

ANA_PATH="$(cd "$(dirname "$RIVET_SO")" && pwd)"

# -------------------------
# Print header
# -------------------------

echo "Rivet bin:   ${RIVET_BIN}"
echo "YODA merge:  ${YODA_MERGE}"
echo "Analysis:    ${ANA}"
echo "Frame:       ${FRAME}"
echo "Meta file:   ${META_JSON}"
echo "Plugin:      ${RIVET_SO}"
echo "HepMC name:  ${HEPMC_BASENAME}"
if [[ $USE_PT2 -eq 1 ]]; then
  echo "pT^2:        ${PT2_MIN} <= pT^2 < ${PT2_MAX}  (GeV^2)"
else
  echo "pT^2:        (no cut)"
fi
echo "Outdir:      ${OUTDIR}"
echo
echo "Found profiles:"
echo "$PROFILES" | sed 's|^|  - |'

# -------------------------
# Stable env for analysis
# -------------------------

export RIVET_METAFILE="$META_JSON"
export RIVET_FRAME="$FRAME"
export RIVET_PHOTONGOING=1
export RIVET_VETO_SPECTATORS=1
export RIVET_SPECTATOR_PMAX=0.001

if [[ $USE_PT2 -eq 1 ]]; then
  export RIVET_PT2_MIN="$PT2_MIN"
  export RIVET_PT2_MAX="$PT2_MAX"
else
  unset RIVET_PT2_MIN || true
  unset RIVET_PT2_MAX || true
fi

# -------------------------
# Main loop
# -------------------------

while IFS= read -r PROFILE_NAME; do
  [[ -z "$PROFILE_NAME" ]] && continue

  YODA_OUT="${OUTDIR}/${PROFILE_NAME}.yoda"
  TMPDIR="${OUTDIR}/_tmp_${PROFILE_NAME}"
  mkdir -p "${TMPDIR}"

  mapfile -t PF_FILES < <(find "$SMASH_DIR" -type f -path "*/${PROFILE_NAME}/${HEPMC_BASENAME}" | sort)

  if [[ ${#PF_FILES[@]} -eq 0 ]]; then
    echo "WARNING: No files found for ${PROFILE_NAME}, skipping." >&2
    rm -rf "${TMPDIR}"
    continue
  fi

  echo
  echo "=== Running Rivet for ${PROFILE_NAME} ==="
  echo "Nfiles:  ${#PF_FILES[@]}"
  echo "Output:  ${YODA_OUT}"
  echo

  YODA_LIST=()
  n_ok=0
  n_fail=0

  for F in "${PF_FILES[@]}"; do
    EVT_TAG="$(echo "$F" | grep -oE 'evt_[0-9]{6}' | head -n1 || true)"
    [[ -z "$EVT_TAG" ]] && EVT_TAG="evt_unknown"

    YODA_ONE="${TMPDIR}/${PROFILE_NAME}_${EVT_TAG}.yoda"
    YODA_LIST+=("${YODA_ONE}")

    echo "-> ${EVT_TAG}: ${F}"
    echo "   RIVET_HEPMC_PATH=\"${F}\" ${RIVET_BIN} --ignore-beams -a \"${ANA}\" --pwd --analysis-path \"${ANA_PATH}\" -o \"${YODA_ONE}\" \"${F}\""

    if RIVET_HEPMC_PATH="${F}" \
       "${RIVET_BIN}" \
        -a "${ANA}" \
        --pwd \
        --analysis-path "${ANA_PATH}" \
        --ignore-beams \
        -o "${YODA_ONE}" \
        "${F}"; then
      ((n_ok++)) || true
    else
      echo "WARNING: rivet failed for file: ${F}" >&2
      ((n_fail++)) || true
    fi
  done

  if [[ ${n_ok} -eq 0 ]]; then
    echo "ERROR: All rivet runs failed for ${PROFILE_NAME}; skipping merge." >&2
    rm -rf "${TMPDIR}"
    continue
  fi

  echo
  echo "Merging ${n_ok} YODAs -> ${YODA_OUT}"
  echo "   ${YODA_MERGE} -o \"${YODA_OUT}\" <${#YODA_LIST[@]} files>"
  "${YODA_MERGE}" -o "${YODA_OUT}" "${YODA_LIST[@]}"

  rm -rf "${TMPDIR}"
  echo "Done ${PROFILE_NAME}: ok=${n_ok} fail=${n_fail}"

done <<< "$PROFILES"

echo
echo "Done. Outputs in: ${OUTDIR}"
