# Analyze OSCAR output from eHIJING and SMASH

`utils/analyze_oscar_output.cpp` is a standalone C++ analyzer for the
OSCAR2013 particle lists produced before and after hadronic transport. It reads
the original eHIJING DIS metadata and writes identified-hadron multiplicity
distributions to a YODA-like text file. It does not require Rivet, ROOT, or the
simulation libraries.

Use separate analyzer invocations for eHIJING and for each SMASH profile. This
keeps the distributions before transport and after transport available for
comparison. See [output layout](../outputs.md) for the run directory structure
and [Rivet analysis](rivet.md) for the separate Rivet workflow.

## Build the analyzer

From the ELECTRA repository root, with a C++17 compiler:

```bash
mkdir -p build/analysis
c++ -std=c++17 -O3 -Wall -Wextra -pedantic \
  utils/analyze_oscar_output.cpp \
  -o build/analysis/analyze_oscar_output
build/analysis/analyze_oscar_output --help
```

On a cluster, compile for the compute-node platform and keep the executable on
a filesystem accessible to the analysis job. The analyzer runs serially.

## Prepare the inputs

Set an absolute parent run path, containing both `ehijing/` and `smash/`:

```bash
export RUN_DIR=/absolute/path/to/output/runs/6
export ANALYZER="$PWD/build/analysis/analyze_oscar_output"
```

### DIS metadata

Both stages use `$RUN_DIR/ehijing/DISKinematics.meta.jsonl`. The eHIJING SLURM
postprocessing job creates this aggregate. For a local run without an aggregate,
the following combines the per-event metadata into a new file. It refuses to
overwrite an existing aggregate and checks for duplicate event IDs:

```bash
python3 - <<'PY'
import json
import os
from pathlib import Path

ehijing = Path(os.environ["RUN_DIR"]) / "ehijing"
paths = sorted((ehijing / "events").rglob("event_*.meta.json"))
if not paths:
    raise SystemExit("No per-event metadata found")
records = {}
for path in paths:
    record = json.loads(path.read_text())
    event = record["event"]
    if event in records:
        raise SystemExit(f"Duplicate metadata event ID: {event}")
    records[event] = record
with (ehijing / "DISKinematics.meta.jsonl").open("x") as out:
    for event in sorted(records):
        out.write(json.dumps(records[event]) + "\n")
PY
```

The analyzer accepts newline-delimited JSON or concatenated, pretty-printed
JSON objects. Every object must contain `event`, `Z`, `A`, `xB`, `Q2`, `y`,
`nu`, `P4`, and `q4`. Four-vectors use `[px, py, pz, E]`, with components in
GeV; `Q2` is in GeV². Keep the generator's original values and frame. Extra
fields are ignored. If duplicate IDs are supplied directly, the analyzer keeps
the first object without reporting the duplication.

### OSCAR particle lists and event IDs

The first twelve particle columns must be, in this order:

```text
t x y z mass p0 px py pz pdg ID charge
```

Additional columns, including eHIJING's production/formation times and SMASH's
extended quantities, are ignored. Momentum, energy and mass use GeV. The
analyzer ignores positions and times; their interface conventions remain fm
and fm/c as described in [unit conventions](../_generated/units.md).
OSCAR1999, binary output, and reordered custom ASCII columns are not supported.

An analyzed block starts with a comment such as `# event 42 out 12` or
`# event 0 ensemble 0 out 12` and ends at an event-end comment. Metadata is
looked up using the first `event_<digits>` component found in the input path
(terminated by a dot, path separator, or the end of the path). Otherwise, the
analyzer uses the event number in the block header.

This means both of these paths select metadata event 42:

```text
ehijing/events/events_00000000-00000999/event_00000042.oscar
smash/events/events_00000000-00000999/event_00000042/profile_<id>/particle_lists.oscar
```

SMASH's internal event numbers can start at zero for each input event, so retain
the parent `event_XXXXXXXX` directories. Flattening or renaming these paths can
silently associate the output with the wrong DIS event. A multi-event file
whose path contains such a component will use that same metadata ID for every
block; generic multi-event files must instead have matching global header IDs.

### Select final SMASH output

Use `particle_lists.oscar`, with one final `out` block per transport replica.
When preparing a SMASH configuration, set:

```yaml
Output:
    Particles:
        Format: ["Oscar2013"]
        Extended: True
        Only_Final: Yes
```

The repository's `input/smash/config_files/config.yaml` does not set
`Only_Final`. Inspect the configuration and files used for your run. The
analyzer counts **every `out` block** as an event; it does not select the last
time snapshot. Files with intermediate snapshots therefore mix times and
normalize by the number of snapshots. For existing files containing multiple
times, prepare final-only particle lists while preserving event associations
before running this analysis. Do not pass collision histories such as
`full_event_history.oscar`.

## Analyze eHIJING output locally

Create a manifest to avoid shell argument limits for large event samples:

```bash
mkdir -p "$RUN_DIR/ehijing/analysis"
find "$RUN_DIR/ehijing/events" -type f -name 'event_*.oscar' \
  | LC_ALL=C sort > "$RUN_DIR/ehijing/analysis/event_manifest.txt"

"$ANALYZER" \
  --meta "$RUN_DIR/ehijing/DISKinematics.meta.jsonl" \
  --file-list "$RUN_DIR/ehijing/analysis/event_manifest.txt" \
  --frame LAB --pt-min 0.0 --pt-max 1.1 --pt-nbins 10 \
  --zh-min 0.05 --zh-max 0.95 --zh-nbins 9 \
  --out "$RUN_DIR/ehijing/analysis/multiplicities.yoda" \
  2> "$RUN_DIR/ehijing/analysis/analyzer.log"
```

The explicit settings above match the SLURM wrapper defaults. Choose the frame
and axes appropriate to your analysis and use the same settings for the SMASH
comparison. The analyzer creates the output file, but not its parent directory;
an existing `--out` file is overwritten.

For a small sample, positional file paths can replace `--file-list`:

```bash
"$ANALYZER" --meta "$RUN_DIR/ehijing/DISKinematics.meta.jsonl" \
  --frame LAB --out /tmp/ehijing-event-42.yoda \
  "$RUN_DIR/ehijing/events/events_00000000-00000999/event_00000042.oscar"
```

Manifest files contain one unquoted path per line. Relative paths resolve from
the analyzer's working directory. Blank lines and lines starting with `#` are
ignored; whitespace is not trimmed. `--file-list` may be repeated, and
`--file-list -` reads paths from standard input. Positional files and manifests
are combined without deduplication.

## Analyze one SMASH profile locally

Select the full profile directory name, including its `profile_` prefix:

```bash
PROFILE=profile_REPLACE_WITH_PROFILE_ID
mkdir -p "$RUN_DIR/smash/analysis/$PROFILE"
find "$RUN_DIR/smash/events" -type f \
  -path "*/$PROFILE/particle_lists.oscar" \
  | LC_ALL=C sort > "$RUN_DIR/smash/analysis/$PROFILE/event_manifest.txt"

"$ANALYZER" \
  --meta "$RUN_DIR/ehijing/DISKinematics.meta.jsonl" \
  --file-list "$RUN_DIR/smash/analysis/$PROFILE/event_manifest.txt" \
  --frame LAB --pt-min 0.0 --pt-max 1.1 --pt-nbins 10 \
  --zh-min 0.05 --zh-max 0.95 --zh-nbins 9 \
  --out "$RUN_DIR/smash/analysis/$PROFILE/multiplicities.yoda" \
  2> "$RUN_DIR/smash/analysis/$PROFILE/analyzer.log"
```

Repeat for each profile. Combining profiles in one invocation averages their
particle lists together. For a comparison before and after transport, restrict
both manifests to the same physical event IDs, especially if SMASH processing
is incomplete. Use a consistent number of transport replicas per physical
event: each replica contributes separately to the normalization, so events
with more replicas receive more weight. The analyzer does not account for
correlations among replicas of the same eHIJING event.

## Submit analysis through SLURM

`slurm-scripts/analysis_submit.sh` submits a file-indexing job followed by a
dependent analysis job. It runs the supplied executable directly on the host.
From the repository root:

```bash
bash slurm-scripts/analysis_submit.sh RUN_ID=6 RUN_DIR="$RUN_DIR" \
  ANALYZER="$ANALYZER" SUBRUN_LABEL=ehijing
```

By default, the wrapper looks for the executable at
`<project-root>/analyze_oscar_output`; `ANALYZER` above selects the build from
this guide. Configure account, partition, resources and paths through
`slurm-scripts/cluster.env` or `key=value` arguments. See the
[SLURM guide](../running/slurm.md) for cluster setup.

For SMASH, reuse the per-profile manifest created above and skip recursive
indexing, which would otherwise combine profiles:

```bash
bash slurm-scripts/analysis_submit.sh RUN_ID=6 RUN_DIR="$RUN_DIR" \
  ANALYZER="$ANALYZER" SUBRUN_LABEL=smash --skip-indexing \
  FILE_LIST="$RUN_DIR/smash/analysis/$PROFILE/event_manifest.txt" \
  ANALYSIS_DIR="$RUN_DIR/smash/analysis/$PROFILE" \
  PT_MIN=0.0 PT_MAX=1.1 PT_NBINS=10 \
  ZH_MIN=0.05 ZH_MAX=0.95 ZH_NBINS=9 FRAME=LAB
```

`FILE_LIST` must already exist and be nonempty when using `--skip-indexing`.
The default output is `ANALYSIS_DIR/multiplicities.yoda`, with scheduler logs
in `ANALYSIS_DIR/logs`. `OUT`, `META_FILE`, and `LOG_DIR` can override these
paths. The wrapper does not compile the analyzer.

## Options and observables

These are the **executable** defaults, which differ from the SLURM defaults
shown in the examples:

| Option | Default | Meaning |
| --- | --- | --- |
| `--meta PATH` | Required | Original eHIJING DIS metadata |
| `--file-list PATH` | None | Input manifest; repeatable; `-` means stdin |
| Positional paths | None | One or more OSCAR particle-list files |
| `--out PATH` | `dndptdz_dndz.yoda` | Output histogram file |
| `--frame NAME` | `BREIT` | `LAB`, `TRF`, or `BREIT`; lowercase also accepted |
| `--pt-min`, `--pt-max`, `--pt-nbins` | `0.0`, `1.1`, `20` | Uniform transverse-momentum axis in GeV |
| `--zh-min`, `--zh-max`, `--zh-nbins` | `0.05`, `1.05`, `10` | Uniform axis for the inclusive $z_h$ spectrum |
| `--xf-min`, `--xf-max` | `0.0`, no upper limit | Parsed, but inactive in the current source |
| `--help`, `-h` | — | Show usage and exit |

At least one input file is required. Axis limits must be finite and increasing,
and bin counts positive. The wrapper defaults to `FRAME=LAB`, `PT_NBINS=10`,
`ZH_MAX=0.95`, and `ZH_NBINS=9`.

The analyzer tracks only these species:

| Hadron | PDG code | Output tag |
| --- | --- | --- |
| $\pi^+$ | 211 | `pip` |
| $\pi^-$ | -211 | `pim` |
| $\pi^0$ | 111 | `pi0` |
| $K^+$ | 321 | `kp` |
| $K^-$ | -321 | `km` |
| Proton | 2212 | `p` |
| Antiproton | -2212 | `pbar` |

For hadron four-momentum $p_h$, it computes

$$
z_h = \frac{P\cdot p_h}{P\cdot q},\qquad
p_T = \left|\boldsymbol p_h -
\frac{\boldsymbol p_h\cdot\boldsymbol q}{|\boldsymbol q|^2}
\boldsymbol q\right|.
$$

Here $P$ and $q$ come from metadata `P4` and `q4`, with Minkowski metric
$(+,-,-,-)$. In the rest frame of $P$, $z_h=E_h/\nu$.
`LAB` uses the stored momenta; `TRF` boosts to the rest frame of `P4`;
`BREIT` uses the additional photon-directed boost implemented in `toFrame`.
The selected frame affects the $p_T$ calculation; its axis is the virtual
photon direction, not necessarily the stored $z$ axis.

Four fixed slices are used for all double-differential distributions:

| $z_h$ interval | Output suffix |
| --- | --- |
| $0.2 < z_h < 0.3$ | `zh0p2_0p3` |
| $0.3 < z_h < 0.4$ | `zh0p3_0p4` |
| $0.4 < z_h < 0.6$ | `zh0p4_0p6` |
| $0.6 < z_h < 0.8$ | `zh0p6_0p8` |

Values exactly on these slice boundaries are excluded. `--zh-*` controls only
the inclusive spectrum; it does not change the fixed slices. The fixed $Q^2$
edges in GeV² are `1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 3, 5, 15`, and the
fixed $x_B$ edges are `0.023, 0.04, 0.055, 0.075, 0.1, 0.14, 0.2, 0.3, 0.4, 0.6`.
Histogram bins include the lower edge and exclude the upper edge.

The current source has `APPLY_XF_CUT = false` and
`APPLY_PID_MOMENTUM_CUT = false`. Thus `--xf-*` does not select particles, and
no species-dependent momentum cut is applied. The analyzer adds no DIS event
cuts; the sample retains its generator selection. The $p_T$ axis limits do
not restrict the inclusive $z_h$, $Q^2$, or $x_B$ spectra. These spectra include
all transverse momenta of the accepted species.

## Read and normalize the output

Each run writes 91 `YODA_HISTO1D_V2` blocks: thirteen per species. The paths are:

| Distribution | Path, with species tag `TAG` and slice suffix `SLICE` |
| --- | --- |
| $(1/N_{\mathrm{evt}})\,dN/(dp_T\,dz_h)$ | `/ELECTRA_MC_2026_DNDPTDZ/dN_dptdz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/(dQ^2\,dz_h)$ | `/ELECTRA_MC_2026_DNDQ2DZ/dN_dQ2dz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/(dx_B\,dz_h)$ | `/ELECTRA_MC_2026_DNDXBDZ/dN_dxbdz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/dz_h$ | `/ELECTRA_MC_2026_DNDZ/dN_dz_TAG` |

For example, the positive-pion spectrum in the first slice is
`/ELECTRA_MC_2026_DNDPTDZ/dN_dptdz_pip_zh0p2_0p3`.

The denominator $N_{\mathrm{evt}}$ is the number of encountered `out` blocks
with matching metadata, including blocks with no accepted hadrons. Unused
metadata entries do not contribute. All particle fills have unit weight; no
cross-section normalization, nuclear ratio, or transport modification ratio is
calculated. The $Q^2$ and $x_B$ distributions use this same global event count,
not the number of DIS events in each $Q^2$ or $x_B$ bin.

For a bin containing $n$ hadrons, **the written `sumw` already stores the
density**: $n/(N_{\mathrm{evt}}\,\Delta p_T\,\Delta z_h)$ for the transverse
spectrum, with the analogous bin widths for the other distributions.
The stored `sumw2` is $n$ times the square of that normalization factor, and
`numEntries` is the raw fill count. Thus a direct text-based plot can use the
bin center, `sumw`, and $\sqrt{\mathrm{sumw2}}$ as the central value and its
counting uncertainty. This uncertainty does not model event or replica
correlations.

The file is YODA-like: a reader that calculates histogram height as
`sumw / bin_width` would divide by the width again. Check the reader's
convention before plotting. `ScaledBy` records only $1/N_{\mathrm{evt}}$;
the bin-width and slice-width factors are also already applied to in-range
rows. Underflow and overflow rows receive only the event normalization.
The written `Total` sums the in-range rows and excludes flows.

Do not combine independently normalized files by adding their bin contents.
For disjoint chunks with identical settings, combine densities using their
matched-event counts as weights. Keep those counts from the logs. Profiles
and stages share the same histogram paths, so retain separate filenames.

## Check a completed analysis

Progress, warnings and summary counters go to standard error. Inspect the saved
log after each run:

- `Events seen` counts all recognized `out` blocks; for final-only eHIJING
  input this should equal the number of selected physical events, and for SMASH
  it should equal the number of selected transport replicas.
- `Events with metadata` is the normalization denominator. `Events vetoed`
  counts blocks whose IDs have no metadata; these blocks are skipped.
- `Malformed lines` counts particle rows that could not be parsed inside
  matched blocks. Resolve unexpected nonzero counts before interpreting results.
- `Filled ... entries` includes underflow and overflow fills. It is not a count
  restricted to the displayed axis range. `Particles seen` also includes PDG
  codes outside the seven tracked species.
- `Particles rejected xF` remains zero while `APPLY_XF_CUT` is disabled.

A successful exit alone is insufficient: the analyzer still writes histograms
when no events match metadata, using a fallback denominator of one. Zero
recognized blocks can indicate an unsupported file format; vetoed blocks can
indicate the wrong aggregate or lost path-based IDs. An unexpected excess of
events can indicate intermediate SMASH snapshots or duplicate inputs. A
`zh mismatch` warning calls for checking the metadata and particle momentum
frame association.
