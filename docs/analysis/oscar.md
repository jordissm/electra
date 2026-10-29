# Analyze OSCAR output from eHIJING and SMASH

`utils/analyze_oscar_output.cpp` is a standalone C++ analyzer for the
OSCAR2013 particle lists produced before and after hadronic transport. It reads
the original eHIJING DIS metadata and writes identified-hadron multiplicity
distributions and charged-hadron time profiles to one YODA text file on every
run. It does not require Rivet, ROOT, or the
simulation libraries.

For configurable cuts, species, multidimensional bins, and mean-value profiles,
use the [YAML analysis mode](yaml-oscar.md). Build that mode with yaml-cpp and
pass `--analysis analysis/configs/hermes_2007_analysis_input.yaml`, or your own
configuration. The remainder of this page describes the legacy mode without
`--analysis` and its input conventions shared by both modes.

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
fields are ignored. Duplicate metadata event IDs are rejected.

### OSCAR particle lists and event IDs

The first twelve particle columns must be, in this order:

```text
t x y z mass p0 px py pz pdg ID charge
```

Multiplicity spectra use these twelve columns. The time profiles additionally
read named `prod_time`, `form_time`, and `prod_time_status` columns when present.
Legacy or SMASH inputs without these columns still produce all histograms;
their time profiles are marked unavailable. Momentum, energy and mass use GeV;
positions and coordinate times use fm and fm/c as described in
[unit conventions](../_generated/units.md).
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
analyzer treats each final `out` block as an event. It rejects multiple `out`
blocks before an event-end marker, rather than mixing intermediate snapshots.
For existing files containing multiple times, prepare final-only particle lists while preserving event associations
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
  PT_MIN=0.0 PT_MAX=1.1 PT_NBINS=10 FRAME=LAB
```

`FILE_LIST` must already exist and be nonempty when using `--skip-indexing`.
The default output is `ANALYSIS_DIR/multiplicities.yoda`, with scheduler logs
in `ANALYSIS_DIR/logs`. `OUT`, `META_FILE`, and `LOG_DIR` can override these
paths. The wrapper does not compile the analyzer.

## HERMES Fig. 2 binning

By default, the inclusive $z_h$, $\nu$, and $Q^2$ spectra use the bin edges
for Fig. 2 of [HERMES, arXiv:0704.3270](https://arxiv.org/abs/0704.3270).
The boundaries are taken from HEPData
[Table 1](https://doi.org/10.17182/hepdata.13387.v1/t1),
[Table 4](https://doi.org/10.17182/hepdata.13387.v1/t4), and
[Table 8](https://doi.org/10.17182/hepdata.13387.v1/t8), also stored under
`analysis/experimental_data/HERMES/R_A/He/`:

| Axis | Bin edges |
| --- | --- |
| $z_h$ | `0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.3` |
| $\nu$ [GeV] | `4, 6, 8, 10, 12, 14, 16, 18, 20, 23.5` |
| $Q^2$ [GeV²] | `1, 1.5, 2, 3, 4, 5, 6, 8, 25` |

The same $Q^2$ edges apply to the existing fixed-$z_h$ double-differential
spectra. Each bin is normalized by its own width, including the wider last
bin. The $p_T$ and $x_B$ axes and the four fixed $z_h$ slices are unchanged.

Supplying any `--zh-min`, `--zh-max`, or `--zh-nbins` option selects a custom
uniform inclusive $z_h$ axis instead. Unspecified values then retain the legacy
executable fallbacks: minimum `0.05`, maximum `1.05`, and `10` bins. For example,
`--zh-min 0.05 --zh-max 0.95 --zh-nbins 9` reproduces the former SLURM axis.
The wrapper uses the HERMES edges unless any `ZH_MIN`, `ZH_MAX`, or `ZH_NBINS`
is supplied; in that case its uniform fallbacks are `0.05`, `0.95`, and `9`.
Remove old explicit axis arguments to use the new default edges.

The existing `/ELECTRA_MC_2026_*` spectra retain their original inclusive
selection and global normalization. The analyzer additionally writes dedicated
`/HERMES_2007/` spectra with the Fig. 2 selections and DIS normalization below.
Use these dedicated outputs for the nuclear ratios. Their axes are fixed to
the table above and are unaffected by the generic `--zh-*`, `--pt-*`, `--xf-*`,
or `--frame` options.

## Fig. 2 selections and multiplicity ratios

The dedicated HERMES outputs check $Q^2>1$ GeV², $W^2=(P+q)^2>4$ GeV²,
and $0<y<0.85$. No additional $x_B$ bound or generator setting is imposed.
The hadron selection requires $x_F>0$ in the photon–target center-of-mass
frame and $2<p<15$ GeV for charged hadrons. Momentum is evaluated in the
rest frame of metadata `P4`, corresponding to the HERMES fixed-target lab.
The tracked neutral pion has a 2.5 GeV lower momentum limit; photon
reconstruction and detector efficiency are not simulated. Fig. 2 itself
uses `pip`, `kp`, and `p`.

| Output axis | Event selection | Hadron selection |
| --- | --- | --- |
| `nu` | $\nu>4$ GeV | $z_h>0.2$ |
| `zh` | $\nu>6$ GeV | $z_h>0.1$ |
| `Q2` | $\nu>6$ GeV | $z_h>0.2$ |

These column-specific thresholds are strict. For example, a hadron in the
first $z_h$ bin contributes to the `zh` spectrum but not the `nu` or `Q2`
spectra. The cut definitions follow sections 4–5 and the Fig. 2 caption of
the paper. There is no extra $p_T$ cut or $x_F$ upper bound.

Each axis writes these paths, where `AXIS` is `zh`, `nu`, or `Q2`:

| Path | Content |
| --- | --- |
| `/HERMES_2007/AXIS/DIS` | Raw accepted DIS counts, including zero-hadron events |
| `/HERMES_2007/AXIS/counts_TAG` | Raw hadron counts; `sumw2` is the sum of squared event-level counts |
| `/HERMES_2007/AXIS/multiplicity_TAG` | Hadron yield divided by the matching DIS count |

The `nu` and `Q2` multiplicities are $N_h/N_\mathrm{DIS}$ in each leptonic
bin. For `zh`, every DIS row contains the same $\nu>6$ event count, and the
multiplicity is $N_h/(N_\mathrm{DIS}\,\Delta z_h)$. Form
$R_A^h=M_A^h/M_D^h$ using independently analyzed nucleus and deuterium files.
Do not divide generic globally normalized densities to obtain these ratios.

Uncertainties use the standard error of the event-level hadron multiplicity,
including zero counts. With $N$ accepted DIS events, $S=\sum_e n_e$ and
$S_2=\sum_e n_e^2$, the variance of the mean is
$(S_2-S^2/N)/(N(N-1))$. The `zh` density also divides the error by
$\Delta z_h$. Transport replicas are treated as separate events; correlations
between replicas of one physical input are not included. The plotting loader
omits bins with no DIS exposure or zero deuterium yield, preserves zero
nuclear yields, and leaves errors undefined for bins with only one DIS event.
The written multiplicity histograms use zero placeholders for bins with no
DIS events and for uncertainties with fewer than two DIS events; inspect the
associated `DIS` histogram or use the loader to distinguish these cases.

Angular acceptance is **off by default**, as selected for this workflow.
Use `--hermes-acceptance rectangular` to apply $|\theta_x|<170$ mrad and
$40<|\theta_y|<140$ mrad to hadrons and the scattered lepton. This is a
geometric window, not a detector response simulation. The optional scattered
lepton is reconstructed as $k'=k-q$ in the target rest frame, using a 27.6 GeV
incoming lepton along `-z` by default, matching ELECTRA's HERMES beam convention.
`--hermes-beam-energy` and `--hermes-beam-direction +z` configure the other
supported beam convention. On SLURM, use `HERMES_ACCEPTANCE`,
`HERMES_BEAM_ENERGY`, and `HERMES_BEAM_DIRECTION` respectively.

## Plot Fig. 2 and R_A

Recompile the analyzer and regenerate each target/scenario's YODA file. Old
files lack the required raw counts, DIS denominators, and selection metadata;
the updated ratio scripts reject them rather than reusing inclusive spectra.
The model-comparison input paths are configured in
`analysis/scripts/model_comparison/R_A/RA_vs_zh_inputs.yaml`.

From the repository root, with Matplotlib installed:

```bash
python3 analysis/scripts/plot_hermes_fig2.py \
  --config analysis/scripts/model_comparison/R_A/RA_vs_zh_inputs.yaml \
  --output-dir /path/to/plots
```

This writes `RA_fig2.pdf` and `RA_fig2.png`: three rows for $\pi^+$, $K^+$,
and $p$, and three columns for $\nu$, $z_h$, and $Q^2$. It overlays the nuclei
and configured model scenarios with the corresponding HERMES tables. Use
`--no-exp` to omit data. Experimental abscissae are the paper's quoted bin
means; neither target ratios nor data comparisons interpolate between bins.

The existing wrappers now also generate this figure:

```bash
bash analysis/run_HERMES_model_comparison_plot_scripts_R_A.sh
bash analysis/run_HERMES_cross_section_profile_comparison_plot_scripts_R_A.sh
```

The cross-section profile wrapper uses its own `RA_vs_zh_inputs.yaml`; its profile
directory can contain `profile_*.yoda` or `tau*.yoda` files, paired by filename
between deuterium and each nucleus. For a direct invocation, supply that
config with `--comparison cross-section-profile` (`formation-time` remains a
compatibility alias). Existing $R_A(z_h)$ grids and the
poster script use the same selected event counts and exact bin alignment.
Different selection/acceptance/beam annotations across targets are rejected.
The separate `e_d` plotting scripts continue to read the generic spectra for
their existing multiplicity comparisons.

For pooled charged-hadron mean production and formation times versus $z_h$,
see the [time analysis guide](times-vs-zh.md). The C++ analyzer reads the OSCAR
time/status columns and includes native YODA time profiles alongside the
multiplicity histograms on every run. These apply the HERMES `zh` selections.
The scripts in `analysis/` only read the combined
YODA files and plot; any target can be analyzed without a nuclear ratio.

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
| `--hermes-acceptance NAME` | `none` | Optional `rectangular` angular window for dedicated HERMES histograms |
| `--hermes-beam-energy E` | `27.6` | Incoming lepton energy in GeV for optional acceptance |
| `--hermes-beam-direction AXIS` | `-z` | Incoming lepton axis in target rest frame: `-z` or `+z` |
| `--pt-min`, `--pt-max`, `--pt-nbins` | `0.0`, `1.1`, `20` | Uniform transverse-momentum axis in GeV |
| `--zh-min`, `--zh-max`, `--zh-nbins` | HERMES edges above | Any of these selects a uniform inclusive $z_h$ axis |
| `--xf-min`, `--xf-max` | `0.0`, no upper limit | Parsed, but inactive in the current source |
| `--help`, `-h` | — | Show usage and exit |

At least one input file is required. Axis limits must be finite and increasing,
and bin counts positive. The wrapper defaults to `FRAME=LAB`, `PT_NBINS=10`,
and the same HERMES inclusive $z_h$ edges as the executable.

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

Values exactly on these slice boundaries are excluded. `--zh-*` controls the
inclusive spectrum and time-profile binning; it does not change the fixed
slices or HERMES multiplicity axes. The fixed $Q^2$
edges in GeV² are `1, 1.5, 2, 3, 4, 5, 6, 8, 25`, and the
fixed $x_B$ edges are `0.023, 0.04, 0.055, 0.075, 0.1, 0.14, 0.2, 0.3, 0.4, 0.6`.
Histogram bins include the lower edge and exclude the upper edge.

The current source has `APPLY_XF_CUT = false` and
`APPLY_PID_MOMENTUM_CUT = false`. Thus `--xf-*` does not select particles, and
no species-dependent momentum cut is applied to the generic spectra. The generic
outputs add no DIS event cuts; the dedicated HERMES outputs apply the selection
above independently of these compile-time switches. The $p_T$ axis limits do
not restrict the inclusive spectra or the sliced $Q^2$ and $x_B$ spectra. These include
all transverse momenta of the accepted species.

## Read and normalize the output

Each run writes 152 objects: 150 `YODA_HISTO1D_V2` blocks (the 45 dedicated
HERMES blocks above plus 105 generic blocks, fifteen per species) and two
charged-hadron time `YODA_PROFILE1D_V2` blocks described in the
[time analysis guide](times-vs-zh.md). The generic histogram paths are:

| Distribution | Path, with species tag `TAG` and slice suffix `SLICE` |
| --- | --- |
| $(1/N_{\mathrm{evt}})\,dN/(dp_T\,dz_h)$ | `/ELECTRA_MC_2026_DNDPTDZ/dN_dptdz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/(dQ^2\,dz_h)$ | `/ELECTRA_MC_2026_DNDQ2DZ/dN_dQ2dz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/(dx_B\,dz_h)$ | `/ELECTRA_MC_2026_DNDXBDZ/dN_dxbdz_TAG_SLICE` |
| $(1/N_{\mathrm{evt}})\,dN/dz_h$ | `/ELECTRA_MC_2026_DNDZ/dN_dz_TAG` |
| $(1/N_{\mathrm{evt}})\,dN/d\nu$ | `/ELECTRA_MC_2026_DNDNU/dN_dnu_TAG` |
| $(1/N_{\mathrm{evt}})\,dN/dQ^2$ | `/ELECTRA_MC_2026_DNDQ2/dN_dQ2_TAG` |

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
- `Events with metadata` is the generic normalization denominator. `Events vetoed`
  counts blocks whose IDs have no metadata; these blocks are skipped.
- `Malformed lines` counts particle rows that could not be parsed inside
  matched blocks. Resolve unexpected nonzero counts before interpreting results.
- `Filled ... entries` includes underflow and overflow fills. It is not a count
  restricted to the displayed axis range. `Particles seen` also includes PDG
  codes outside the seven tracked species.
- `Particles rejected xF` remains zero while `APPLY_XF_CUT` is disabled.
  This counter describes the generic spectra; the dedicated HERMES outputs
  always enforce $x_F>0$.
- `HERMES accepted DIS` counts the common DIS selection before the
  column-specific $\nu$ thresholds. Inspect the dedicated `DIS` histograms
  for the denominators actually used in each plotted bin.

A successful exit alone is insufficient: the analyzer still writes histograms
when no events match metadata, using a fallback denominator of one. Zero
recognized blocks can indicate an unsupported file format; vetoed blocks can
indicate the wrong aggregate or lost path-based IDs. An unexpected excess of
events can indicate intermediate SMASH snapshots or duplicate inputs. A
`zh mismatch` warning calls for checking the metadata and particle momentum
frame association.
