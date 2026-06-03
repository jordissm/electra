#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage:
  bash slurm-scripts/analysis_submit.sh RUN_ID [--skip-indexing] [key=value ...]
  bash slurm-scripts/analysis_submit.sh RUN_ID=<RUN_ID> [--skip-indexing] [key=value ...]

Examples:
  bash slurm-scripts/analysis_submit.sh 6
  bash slurm-scripts/analysis_submit.sh RUN_ID=6 PT_NBINS=10 ZH_NBINS=10

Options can also be supplied as environment variables:
  SLURM_CONFIG, PROJECT_ROOT, OUTPUT_HOST, RUNS_DIR, RUN_DIR, ACCOUNT, PARTITION,
  INDEX_TIME_LIMIT, ANALYSIS_TIME_LIMIT, CPUS_PER_TASK, MEMORY, ANALYZER,
  OSCAR_PATTERN, PT_MIN, PT_MAX, PT_NBINS, ZH_MIN, ZH_MAX, ZH_NBINS,
  FRAME, OUT, SKIP_INDEXING, SUBRUN_LABEL

Set SKIP_INDEXING=1 to reuse an existing FILE_LIST and submit only the analysis job.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLURM_CONFIG="${SLURM_CONFIG:-$SCRIPT_DIR/cluster.env}"

if [[ -f "$SLURM_CONFIG" ]]; then
    # shellcheck source=/dev/null
    set +u
    source "$SLURM_CONFIG"
    set -u
fi

# -----------------------------
# Parse positional run id and key=value arguments
# -----------------------------
RUN_ID="${RUN_ID:-}"

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
            ;;
        --skip-indexing)
            export SKIP_INDEXING=1
            ;;
        *=*)
            key="${arg%%=*}"
            val="${arg#*=}"
            export "$key"="$val"
            case "$key" in
                RUN_ID)
                    RUN_ID="$val"
                    ;;
            esac
            ;;
        *)
            if [[ -z "$RUN_ID" ]]; then
                RUN_ID="$arg"
            else
                echo "Warning: ignoring extra positional argument '$arg'" >&2
            fi
            ;;
    esac
done

if [[ -z "$RUN_ID" && -n "${RUN_DIR:-}" ]]; then
    RUN_ID="$(basename "$RUN_DIR")"
fi

if [[ -z "$RUN_ID" ]]; then
    usage >&2
    echo >&2
    echo "Error: provide a run ID." >&2
    exit 1
fi

# -----------------------------
# User-tunable parameters
# -----------------------------
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
OUTPUT_HOST="${OUTPUT_HOST:-$PROJECT_ROOT/output}"
RUNS_DIR="${RUNS_DIR:-$OUTPUT_HOST/runs}"

JOB_NAME="${JOB_NAME:-${JOB_NAME_PREFIX:-electra}:analysis}"
ACCOUNT="${ACCOUNT:-qgp}"
PARTITION="${PARTITION:-qgp}"
INDEX_TIME_LIMIT="${INDEX_TIME_LIMIT:-00:30:00}"
ANALYSIS_TIME_LIMIT="${ANALYSIS_TIME_LIMIT:-${DEFAULT_TIME_LIMIT:-12:00:00}}"
CPUS_PER_TASK="${CPUS_PER_TASK:-${DEFAULT_CPUS_PER_TASK:-1}}"
MEMORY="${MEMORY:-${DEFAULT_MEMORY:-2G}}"
SKIP_INDEXING="${SKIP_INDEXING:-0}"
INDEX_MEMORY="${INDEX_MEMORY:-1G}"

ANALYZER="${ANALYZER:-$PROJECT_ROOT/analyze_oscar_dndptdz}"
OSCAR_PATTERN="${OSCAR_PATTERN:-*.oscar}"
PT_MIN="${PT_MIN:-0.0}"
PT_MAX="${PT_MAX:-1.1}"
PT_NBINS="${PT_NBINS:-10}"
FRAME="${FRAME:-BREIT}"

if [[ -n "${RUN_DIR:-}" ]]; then
    :
elif [[ "$RUN_ID" = /* || "$RUN_ID" == .* || "$RUN_ID" == */* ]]; then
    RUN_DIR="$RUN_ID"
else
    RUN_DIR="$RUNS_DIR/$RUN_ID"
    LEGACY_RUN_DIR="$PROJECT_ROOT/runs/$RUN_ID"
    if [[ ! -d "$RUN_DIR" && -d "$LEGACY_RUN_DIR" ]]; then
        RUN_DIR="$LEGACY_RUN_DIR"
    fi
fi

if [[ -d "$RUN_DIR" ]]; then
    RUN_DIR="$(cd "$RUN_DIR" && pwd)"
fi
EHIJING_DIR="$RUN_DIR/ehijing"
EVENTS_DIR="$EHIJING_DIR/events"
META_FILE="${META_FILE:-$EHIJING_DIR/DISKinematics.meta.jsonl}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$RUN_DIR/analysis}"
LOG_DIR="${LOG_DIR:-$ANALYSIS_DIR/logs}"
FILE_LIST="${FILE_LIST:-$ANALYSIS_DIR/particle_lists_files.txt}"
OUT="${OUT:-$ANALYSIS_DIR/dndptdz.yoda}"

if [[ ! -d "$RUN_DIR" ]]; then
    echo "Error: run directory not found: $RUN_DIR" >&2
    if [[ -n "${LEGACY_RUN_DIR:-}" && "$LEGACY_RUN_DIR" != "$RUN_DIR" ]]; then
        echo "       Also checked: $LEGACY_RUN_DIR" >&2
    fi
    exit 1
fi
if [[ ! -d "$EVENTS_DIR" ]]; then
    echo "Error: eHIJING events directory not found: $EVENTS_DIR" >&2
    exit 1
fi
if [[ ! -f "$META_FILE" ]]; then
    echo "Error: DIS kinematics metadata not found: $META_FILE" >&2
    exit 1
fi
if [[ ! -x "$ANALYZER" ]]; then
    echo "Error: analyzer executable not found or not executable: $ANALYZER" >&2
    exit 1
fi

mkdir -p "$ANALYSIS_DIR" "$LOG_DIR"

echo "Submitting combined OSCAR analysis:"
echo "  run id       : $RUN_ID"
echo "  run dir      : $RUN_DIR"
echo "  events dir   : $EVENTS_DIR"
echo "  meta file    : $META_FILE"
echo "  file list    : $FILE_LIST"
echo "  output       : $OUT"
echo "  analyzer     : $ANALYZER"
echo "  skip indexing: $SKIP_INDEXING"

# -----------------------------
# Step 1: index OSCAR files
# -----------------------------
if [[ "$SKIP_INDEXING" == "1" || "$SKIP_INDEXING" == "true" || "$SKIP_INDEXING" == "TRUE" ||
      "$SKIP_INDEXING" == "yes" || "$SKIP_INDEXING" == "YES" ]]; then
    if [[ ! -s "$FILE_LIST" ]]; then
        echo "Error: SKIP_INDEXING=$SKIP_INDEXING but FILE_LIST is missing or empty: $FILE_LIST" >&2
        exit 1
    fi
    INDEX_JOB_ID=""
else
INDEX_JOB_ID=$(
sbatch --parsable <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:index
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${INDEX_TIME_LIMIT}
#SBATCH --cpus-per-task=1
#SBATCH --mem=${INDEX_MEMORY}
#SBATCH -o ${LOG_DIR}/index_%j.out
#SBATCH -e ${LOG_DIR}/index_%j.err

set -euo pipefail

EVENTS_DIR="${EVENTS_DIR}"
FILE_LIST="${FILE_LIST}"
OSCAR_PATTERN="${OSCAR_PATTERN}"

mkdir -p "\$(dirname "\${FILE_LIST}")"

LC_ALL=C find "\${EVENTS_DIR}" -type f -name "\${OSCAR_PATTERN}" | sort > "\${FILE_LIST}"

NFILES=\$(wc -l < "\${FILE_LIST}")
echo "Indexed \${NFILES} OSCAR files into \${FILE_LIST}"

if [[ "\${NFILES}" -eq 0 ]]; then
    echo "Error: no OSCAR files matching '\${OSCAR_PATTERN}' under \${EVENTS_DIR}" >&2
    exit 1
fi
EOF
)
fi

# -----------------------------
# Step 2: run analysis after indexing succeeds
# -----------------------------
SBATCH_DEPENDENCY=()
if [[ -n "$INDEX_JOB_ID" ]]; then
    SBATCH_DEPENDENCY=(--dependency=afterok:${INDEX_JOB_ID})
fi

ANALYSIS_JOB_ID=$(
sbatch --parsable "${SBATCH_DEPENDENCY[@]}" <<EOF
#!/bin/bash
#SBATCH -J ${JOB_NAME}:run
#SBATCH -A ${ACCOUNT}
#SBATCH -p ${PARTITION}
#SBATCH -t ${ANALYSIS_TIME_LIMIT}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem=${MEMORY}
#SBATCH -o ${LOG_DIR}/analysis_%j.out
#SBATCH -e ${LOG_DIR}/analysis_%j.err

set -euo pipefail

ANALYZER="${ANALYZER}"
META_FILE="${META_FILE}"
FILE_LIST="${FILE_LIST}"
OUT="${OUT}"
PT_MIN="${PT_MIN}"
PT_MAX="${PT_MAX}"
PT_NBINS="${PT_NBINS}"
FRAME="${FRAME}"

"\${ANALYZER}" \
    --meta "\${META_FILE}" \
    --file-list "\${FILE_LIST}" \
    --out "\${OUT}" \
    --pt-min "\${PT_MIN}" \
    --pt-max "\${PT_MAX}" \
    --pt-nbins "\${PT_NBINS}" \
    --frame "\${FRAME}"
EOF
)

if [[ -n "$INDEX_JOB_ID" ]]; then
echo "Submitted index job   : ${INDEX_JOB_ID}"
echo "Submitted analysis job: ${ANALYSIS_JOB_ID} (afterok:${INDEX_JOB_ID})"
else
    echo "Skipped index job; using existing file list: ${FILE_LIST}"
    echo "Submitted analysis job: ${ANALYSIS_JOB_ID}"
fi
