# Charged-hadron production and formation times versus z_h

Event processing lives in `utils/analyze_oscar_output.cpp`. Every run reads
OSCAR and DIS metadata once and writes all multiplicity histograms and native
YODA time profiles together in the same file. The scripts under
`analysis/scripts/cross_section_profile_comparison/times_vs_zh/` only read those
YODA files and plot. No OSCAR files, DIS metadata, CSVs, or JSON sidecars are
needed on the plotting machine.

Any target can be analyzed without a deuterium reference or nuclear ratio.
All accepted $\pi^\pm$, $K^\pm$, $p$ and $\bar p$ enter **one pooled
charged-hadron average**, with equal weight per hadron. Analyze distinct
samples/targets separately and overlay their YODA files as desired.

## Definition and selection

Both means use exactly the same hadrons: `prod_time_status = 1`. Status `0`
(unavailable production reference) and status `2` (spectators) are excluded
from both averages. A genuine zero production time with status `1` is kept.
Neutral particles and other species are excluded. Invalid available times
stop the analysis rather than silently biasing either mean.

The times are the stored OSCAR coordinate times in fm/c, without a boost,
origin subtraction, clipping, or Lorentz factor. Finite negative and zero
times are retained. They are neither proper times nor elapsed times from the
hard interaction. Compare samples in the same frame with compatible spacetime
origins; see the [unit conventions](../_generated/units.md).

The cuts reuse the existing C++ analyzer's HERMES selection:

- $Q^2>1$ GeV², $W^2=(P+q)^2>4$ GeV², $0<y<0.85$, and $\nu>6$ GeV.
- $z_h=(P\cdot p_h)/(P\cdot q)>0.1$, from metadata `P4` and `q4`.
- $x_F>0$ in the photon–target center-of-mass frame.
- $2<p_h<15$ GeV in the rest frame of `P4`, for all six included species.

Angular acceptance is **off by default**, as in the existing analyzer.
`--hermes-acceptance rectangular` enables its hadron and scattered-lepton
window: $|\theta_x|<170$ mrad, $40<|\theta_y|<140$ mrad. Beam defaults are
27.6 GeV along `-z` in the target rest frame; use `--hermes-beam-energy` and
`--hermes-beam-direction` to configure them. `--frame` affects generic spectra,
not the stored times or HERMES selections.

Default bin edges are `0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.3`.
Bins include their lower edge and exclude their upper edge; the strict
$z_h>0.1$ cut additionally excludes exactly `0.1`. As in the generic analyzer,
any `--zh-min`, `--zh-max`, or `--zh-nbins` option selects uniform time-profile
bins (executable fallbacks: `0.05`, `1.05`, `10`). Selections remain unchanged.
Underflow and overflow moments are retained separately in the YODA profiles.

## Process OSCAR on the cluster

Build the standalone utility with a C++17 compiler, without physics libraries
or the YODA library:

```bash
mkdir -p build/analysis
c++ -std=c++17 -O3 -Wall -Wextra -pedantic \
  utils/analyze_oscar_output.cpp -o build/analysis/analyze_oscar_output
```

Deploy the compiled utility or `utils/analyze_oscar_output.cpp` to the data
host. Use current eHIJING OSCAR with named `prod_time`, `form_time`, and
`prod_time_status` columns and the matching `DISKinematics.meta.jsonl`.
Prepare metadata as described in the [OSCAR guide](oscar.md#dis-metadata).
The analyzer checks named time columns, time units when a units header is
present, block particle counts, event endings, and duplicate input paths and
metadata IDs. Missing DIS metadata for events with time columns is an error. A single output sample must contain one target.

As in the existing analyzer, an `event_XXXXXXXX` path component overrides
local block event numbers. Preserve the original directories. File manifests
should contain absolute paths; relative entries resolve from the analyzer's
working directory, matching the existing multiplicity workflow.

```bash
RUN_DIR=/absolute/path/to/run
ANALYSIS_DIR="$RUN_DIR/ehijing/analysis"
mkdir -p "$ANALYSIS_DIR"
find "$RUN_DIR/ehijing/events" -type f -name 'event_*.oscar' \
  | sort > "$ANALYSIS_DIR/event_manifest.txt"
build/analysis/analyze_oscar_output \
  --meta "$RUN_DIR/ehijing/DISKinematics.meta.jsonl" \
  --file-list "$ANALYSIS_DIR/event_manifest.txt" \
  --out "$ANALYSIS_DIR/multiplicities.yoda"
```

The standard SLURM analysis invocation produces the same combined output:

```bash
bash slurm-scripts/analysis_submit.sh RUN_ID=6 RUN_DIR="$RUN_DIR" \
  ANALYZER="$PWD/build/analysis/analyze_oscar_output" \
  OSCAR_PATTERN='event_*.oscar'
```

This defaults to `RUN_DIR/ehijing/analysis/multiplicities.yoda`, containing all
152 YODA objects. `OUT`, `ANALYSIS_DIR`, `FILE_LIST`, `--skip-indexing`, and the
existing `HERMES_*` settings remain available. `ZH_*` overrides select uniform
inclusive and time-profile bins; the wrapper's uniform fallbacks are `0.05`,
`0.95`, `9`. The standalone executable retains its default output filename
`dndptdz_dndz.yoda`; either destination contains all observables.

## YODA output and local plotting

Each output contains the existing 150 `YODA_HISTO1D_V2` objects plus these two
`YODA_PROFILE1D_V2` objects:

| Path | Profile ordinate |
| --- | --- |
| `/HERMES_2007/zh/production_time_charged` | Stored production coordinate time [fm/c] |
| `/HERMES_2007/zh/formation_time_charged` | Stored formation coordinate time [fm/c] |

Each bin stores `sumw`, `sumw2`, `sumwx`, `sumwx2`, `sumwy`, `sumwy2`, and
`numEntries`, with $x=z_h$, $y=t$, and unit weights. Thus `sumw = N_h` and
`sumwy = sum(t_h)`; the plotted mean is **`sumwy / sumw`**. There is no DIS
normalization or bin-width factor. Events with more accepted hadrons contribute
more entries. Total and flow rows retain the same additive moments. Merge only
compatible samples and raw moments, never precomputed means.

Annotations record selection, particle species, production availability,
coordinate-time units, angular/beam settings, target, and input/exclusion
counts. Plots require matching annotations and binning across curves. Empty
bins have zero raw moments and plot as gaps rather than zero means. Plots show
means at bin centers without error bars; hadron spread and event/replica
correlations are not interpreted as uncertainties on the means.

Copy the resulting YODA files to the plotting machine. With Python 3.10+ and
Matplotlib, plot them directly:

```bash
python3 analysis/scripts/cross_section_profile_comparison/times_vs_zh/plot_times_vs_zh.py \
  --inputs /path/to/ehijing.yoda /path/to/another_sample.yoda \
  --labels "eHIJING" "Another sample" \
  --output-dir analysis/output/cross_section_profile_comparison/times_vs_zh/plots
```

Alternatively, copy
`analysis/scripts/cross_section_profile_comparison/times_vs_zh/times_vs_zh_inputs.example.json`
to a working plot config and list each sample's `yoda` path and `label`. Paths
resolve relative to the config. Run the plotting-only wrapper:

```bash
bash analysis/run_cross_section_profile_comparison_times_vs_zh.sh \
  --config /path/to/times_vs_zh_inputs.json \
  --output-dir analysis/output/cross_section_profile_comparison/times_vs_zh/plots
```

Both entry points write `charged_hadron_times_vs_zh.pdf` and `.png`, with one
production-time panel and one formation-time panel. Set `PYTHON` to choose the
wrapper's plotting interpreter. The existing multiplicity YODA files lack time
moments and must be regenerated with the updated analyzer for these plots.

## Input limitations and validation

Standard SMASH extended particle lists expose `begin_form_time` and omit
`prod_time_status`. Multiplicity processing continues for these files and for
legacy twelve-column files. Both time profiles are still written with zero raw
moments and `TimeColumns: unavailable`; an effective transport profile start is
not substituted for a known production reference.

When only some event blocks contain all time/status columns, the time profiles
contain the available contributions and are marked `TimeColumns: partial`.
`TimeColumnsAvailableEvents` and `TimeColumnsMissingEvents` expose coverage.
The time plotter rejects unavailable or partial profiles, while the multiplicity
plots remain usable. Inputs with complete named fields are marked `complete`;
events passing no time selection simply leave empty bins. All outputs are
written even when no hadrons pass the time selection or no production times
are available. Other final-only OSCAR samples must preserve the named fields
and their meaning to supply time averages.

In `OSCAR` formation mode, changing only a cross-section profile does not
change the imported eHIJING time assignments. A source curve can therefore be
shared by those profiles. No new times or differences are inferred from profile
IDs. Comparing distinct recorded samples requires the actual time/status data.

Run synthetic integration checks without simulation event generation:

```bash
python3 -B -m unittest discover -s utils/tests -p test_oscar_times.py -v
```

The tests compile the C++ utility, check raw YODA moments and pooled means,
compare time and multiplicity cuts, exercise standard SLURM submission
using a mock scheduler, and verify that plotting works with only YODA inputs.
