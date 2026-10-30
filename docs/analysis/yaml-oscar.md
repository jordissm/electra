# Configurable OSCAR analysis with YAML

`utils/analyze_oscar_output.cpp --analysis FILE.yaml` reads the histogram
definitions from YAML. You can request one-dimensional distributions,
multidimensional distributions, or mean-value profiles, with independent
selections for each. One invocation processes one target and one beam setup;
run the same configuration separately on eHIJING, each SMASH profile, and each
target. Inputs and event matching follow the [OSCAR guide](oscar.md).

Without `--analysis`, the historical command-line behavior and output names
are preserved. YAML mode writes only the requested objects. It rejects the
legacy `--frame`, `--pt-*`, `--zh-*`, `--xf-*`, and `--hermes-*` options so that
the YAML is the sole source of analysis settings.

## Build and run

YAML mode requires yaml-cpp. The build script downloads the official 0.8.0
source archive, verifies its pinned SHA-256, and builds and installs a private
static copy under `<build-directory>/deps/yaml-cpp-0.8.0/install`. Dependency
sources are not bundled in the utility directory and are not taken from SMASH.
With CMake and a C++17 compiler available, run this from the repository root,
or rerun the same script in an installed utility directory:

```bash
bash utils/build_analysis.sh --jobs 2

utils/analyze_oscar_output \
  --analysis analysis/configs/hermes_2007_analysis_input.yaml \
  --meta /absolute/run/ehijing/DISKinematics.meta.jsonl \
  --file-list /absolute/run/ehijing/analysis/event_manifest.txt \
  --out /absolute/run/ehijing/analysis/hermes_2007.yoda
```

Packaged installations also ship the example YAML files under
`<utils-directory>/analysis-configs/`. Their CMake source directory is that
utility directory rather than the checkout's `utils/` directory.

`install.sh` calls this build script automatically after copying the utilities,
honoring `--prefix` and `--utils`. The executable is placed next to the script,
with incremental CMake artifacts under `<utils-directory>/build/analysis`.
Run `bash /absolute/path/to/utils/build_analysis.sh` after source/header changes;
it works from any current directory and keeps the previous executable if a
build fails. `--jobs N`, `--build-dir PATH`, and `--output PATH` customize the
build. Without `--jobs`, parallelism uses `CMAKE_BUILD_PARALLEL_LEVEL` if set,
otherwise `nproc`, then macOS's `sysctl -n hw.ncpu`, and finally a fallback of 2.
Additional CMake configure arguments follow `--`, for example
`bash utils/build_analysis.sh -- -DCMAKE_CXX_COMPILER=g++`.

The installer accepts `--skip-analysis-build` to defer host compilation.
On clusters, compile with tools compatible with the compute-node platform.
The first build needs internet access; subsequent builds reuse verified cached
sources and build the dependency incrementally. No administrator privileges
are needed. Keep the build directory to retain that cache. The dependency's
MIT license is installed under `share/licenses/yaml-cpp/LICENSE` in its private
installation prefix.

For offline builds, supply the official source archive:

```bash
bash utils/build_analysis.sh --yaml-cpp-archive /absolute/path/to/yaml-cpp-0.8.0.tar.gz
```

Or use an existing installation without downloading or building yaml-cpp:

```bash
bash utils/build_analysis.sh --yaml-cpp-prefix /absolute/path/to/yaml-cpp-install
```

The prefix should contain its CMake package in `lib/cmake/yaml-cpp`,
`lib64/cmake/yaml-cpp`, or `share/cmake/yaml-cpp`. An explicitly selected shared
library must be available on the execution host too. These options are mutually
exclusive. `ELECTRA_YAML_CPP_ARCHIVE` and `ELECTRA_YAML_CPP_PREFIX` provide the
same settings through the environment, including when `install.sh` invokes the
build script automatically. A local archive must match the same pinned release
checksum; it is not a mechanism for selecting an arbitrary dependency version.

Direct CMake builds are also available if yaml-cpp is already installed:

```bash
cmake -S utils -B build/analysis -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/absolute/path/to/yaml-cpp-install
cmake --build build/analysis --parallel 2
```

That alternative places the binary in `build/analysis/` instead of next to the
sources; set `ANALYZER` to that path when using the SLURM wrapper.

Copy the complete utility directory, including its `cmake/` helper, when
deploying its sources to a cluster. The default build links yaml-cpp statically,
so the compute nodes do not need a yaml-cpp shared library. The former
`ELECTRA_USE_SYSTEM_YAML_CPP` and `ELECTRA_YAML_CPP_SOURCE_DIR` options are no
longer used; choose the build script's dependency options or CMake's package
prefix instead.

The analyzer is built and executed on the host by the installer and SLURM
wrapper. Installing yaml-cpp only inside Docker does not satisfy that host
build. A private host installation keeps these workflows independent of the
physics image; container-only builds can instead use their own installed
yaml-cpp package through the existing-prefix option.

The original direct C++ compilation command still builds legacy mode.
The following alternative direct build requires a separate installed yaml-cpp
and pkg-config; use the build script above for automatic dependency installation:

```bash
c++ -std=c++17 -O3 -Wall -Wextra -pedantic -DELECTRA_WITH_YAML \
  utils/analyze_oscar_output.cpp -o build/analysis/analyze_oscar_output \
  $(pkg-config --cflags --libs yaml-cpp)
```

The SLURM wrapper passes the YAML through without injecting legacy axis or
acceptance defaults:

```bash
bash slurm-scripts/analysis_submit.sh RUN_ID=6 \
  ANALYZER="$PWD/utils/analyze_oscar_output" \
  ANALYSIS_INPUT="$PWD/analysis/configs/hermes_2007_analysis_input.yaml"
```

The YAML path is converted to an absolute path before submission and must be
readable from the compute node. The executable must also be available there;
an explicitly selected system shared yaml-cpp needs its runtime there too.
The wrapper executes the analyzer directly on the host.
The checkout default is `<project-root>/utils/analyze_oscar_output`. During
cluster installation, the installer captures the actual installed utility path
in the copied analysis submit script, including custom `--utils` locations.
It also captures the installer-selected `--output` directory for run discovery.
An explicit `ANALYZER` environment variable or submission argument overrides it.

## Define a new figure

This complete example requests a double-differential hadron multiplicity in
three virtual-photon-energy intervals and a mean transverse-momentum profile:

```yaml
version: 1
name: MY_ANALYSIS
description: Custom distributions for a 27.6 GeV fixed-target sample.
beam: {energy: 27.6, mass: 0.00051099895, direction: -z}
frame: TRF
weighting: unit
species:
  pip: [211]
  pim: [-211]
  charged: {charge: nonzero}
event_cuts:
  Q2: {min: 1}
  W2: {min: 4}
  y: {max: 0.85}
  nu: {min: 6, max: 23.5}
hadron_cuts:
  zh: {min: 0.2}
  p: {min: 2, max: 15}
histograms:
  - name: zh_pt2_nu
    kind: multiplicity
    normalization: per_dis
    axes:
      - {variable: zh, edges: [0.2, 0.3, 0.4, 0.6, 0.8, 1], density: true}
      - {variable: pT2, edges: [0, 0.2, 0.5, 1, 2], density: true}
      - {variable: nu, edges: [6, 10, 16, 23.5]}
  - name: mean_pt2
    kind: profile
    quantity: pT2
    species: [pip, pim]
    axes:
      - {variable: zh, min: 0.2, max: 1, bins: 8}
```

The first axis is the horizontal histogram axis. Every combination of bins
on the remaining axes produces a separate YODA object. This preserves all
multidimensional cells while allowing ordinary `Histo1D` and `Profile1D`
readers to consume the output. Axis order is arbitrary: event variables may
appear first or in any of the slicing positions.

An axis accepts either `edges: [...]` or `min`, `max`, and `bins` for uniform
spacing. Edges must be finite and strictly increasing. Bins include their
lower edge and exclude their upper edge. `density: true` divides the
multiplicity by the width of that axis, including a slicing axis; its default
is `false`. For the example, the result is
`N_h / (N_DIS * delta_zh * delta_pT2)` in each `nu` interval.
Use `density: false` for an integrated bin yield. Profiles cannot use density
normalization. `normalization: counts` requests only raw counts and DIS
denominators and also prohibits density normalization.

Histogram names, the analysis name, and species names accept letters, digits,
underscores and hyphens. Unknown keys, duplicate names or mapping keys, invalid
variables, empty species groups, and oversized allocations are errors. The
allocation limit is one million species/bin cells across the configuration,
including the first axis's flow bins.

## Selections, species, and frames

Global `event_cuts` select inclusive DIS events. Global `hadron_cuts` select
hadrons within those events. Each histogram can override either mapping by
variable. An override **replaces the whole range for that variable**; other
cuts remain inherited. Use `null` to remove an inherited cut. For example:

```yaml
event_cuts:
  nu: {min: 4, max: 23.5}  # Replace the common nu range.
hadron_cuts:
  zh: {min: 0.1}          # Replace the common zh range.
  p: null                 # Remove the common momentum cut.
```

Bounds are strict by default (`min < value < max`), independently of the
histogram bin convention. Set `min_inclusive: true` or `max_inclusive: true`
on a range to include that endpoint. Omit either bound for an open range.
Missing cuts impose no restriction. In particular, a histogram axis range is
not a global cut on other histograms.

| Variables | Definition and units |
| --- | --- |
| `Q2`, `xB`, `y`, `nu` | Original DIS metadata; GeV², dimensionless, dimensionless, GeV |
| `W2`, `W` | `(P + q)^2` and its positive square root, GeV² and GeV |
| `A`, `Z` | Target metadata, useful for explicit event selection |
| `lepton_E`, `lepton_p` | Scattered-lepton energy and momentum in the target rest frame, GeV |
| `lepton_theta`, `lepton_abs_theta_x`, `lepton_abs_theta_y` | Scattered-lepton angles to the signed beam axis in the target rest frame, radians |
| `zh` | `(P . p_h)/(P . q)`, equal to `E_h/nu` in the rest frame of `P` |
| `p`, `E` | Hadron momentum magnitude and energy in `frame`, GeV |
| `pT`, `pT2` | Hadron momentum transverse to `q` in `frame`, GeV and GeV² |
| `xF` | `2 p_L*/W`, along `q*` in the rest frame of `P + q` |
| `theta`, `abs_theta_x`, `abs_theta_y` | Hadron polar angle and absolute projected angles to the configured signed z axis in `frame`, radians |
| `rapidity` | Hadron rapidity along `q` in `frame` |

Event cuts and DIS binning use only the event variables (the first five rows).
Hadron cuts and histogram axes can also use hadron variables. Put event
selection in `event_cuts` to apply it to the denominator; placing an event
variable in `hadron_cuts` deliberately restricts only the numerator.

`frame` is required and can be `LAB` (stored generator frame), `TRF` (rest
frame of metadata `P`), or `BREIT` (the existing analyzer's Breit boost).
`beam.energy`, `beam.mass` and `beam.direction` are required; direction is
`+z` or `-z` **in the target rest frame**. Scattered leptons are reconstructed
there from `k' = k - q`. Configure the actual beam axis used by the simulation.
For fixed-target angular acceptance, use `frame: TRF`. Hadron angles in a
different frame use that frame's signed z axis, not an automatically transformed
detector geometry. Energies and masses use GeV throughout. The nuclear/DIS
conventions for `P` must match the generator's metadata.

Species are explicit PDG lists or inclusive charge selections:

```yaml
species:
  pion_sum: [211, -211]
  hplus: {charge: positive}
  hminus: {charge: negative}
  charged: {charge: nonzero}
```

Inclusive groups use the OSCAR charge column and accept hadron PDG codes
`100 <= abs(pdg) < 10^9`, excluding photons, leptons and nuclear fragments.
They include all final hadrons meeting that rule, including any spectator
protons present in the input; use appropriate momentum/fragmentation cuts.
Explicit lists can request any PDG code. Groups may overlap; each group's
histogram is separate. A histogram's optional `species` list selects named
groups; omission selects all groups. Species-specific cuts can be expressed
with separate histogram definitions selecting the relevant groups.

No angular acceptance is implicit. For example, rectangular HERMES acceptance
can be expressed by adding these **cuts**, with `frame: TRF`:

```yaml
event_cuts:
  lepton_abs_theta_x: {max: 0.170}
  lepton_abs_theta_y: {min: 0.040, max: 0.140}
hadron_cuts:
  abs_theta_x: {max: 0.170}
  abs_theta_y: {min: 0.040, max: 0.140}
```

These cuts describe geometric acceptance with unit efficiency inside the
window. There is no detector smearing, efficiency-map application, unfolding,
QED correction, decay reconstruction, or ancestry-based background subtraction.
Choose input particle lists and selections consistent with the publication's
correction and particle definitions. The analyzer does not change the
simulation's decay settings or physics model.

## Denominators, errors, and output

For each multidimensional cell the denominator contains events passing that
histogram's event cuts and **all its event-variable bins**. Hadron-variable
bins never restrict the DIS denominator. In particular, a zero-hadron event
still contributes, and a `zh` axis uses the same DIS sample in every bin.

Multiplicities are accumulated as event hadron counts `n_e`, not as independent
hadron trials. Unit-weight errors are the standard error of those event
counts, including zeros. For `weighting: metadata`, an optional positive,
finite top-level `weight` in each DIS metadata object supplies `w_e`; a missing
weight defaults to one. `weighting: unit` rejects non-unit metadata weights.
The weighted mean and squared standard error are:

```text
mu = sum(w_e * n_e) / sum(w_e)
variance(mu) = N/(N-1) * sum(w_e^2 * (n_e-mu)^2) / sum(w_e)^2
```

Here `N` is the number of eligible events. Density axes divide the mean by
their combined bin width and the variance by its square. Empty denominator
bins have `nan` multiplicity; fewer than two events give `nan` squared error.
This distinguishes an undefined result from a physical zero yield.

For each slice, output paths have the following forms:

```text
/MY_ANALYSIS/zh_pt2_nu/pT2_bin0/nu_bin1/DIS
/MY_ANALYSIS/zh_pt2_nu/pT2_bin0/nu_bin1/counts_pip
/MY_ANALYSIS/zh_pt2_nu/pT2_bin0/nu_bin1/multiplicity_pip
/MY_ANALYSIS/mean_pt2/mean_pT2_pip
```

The slice suffixes are omitted for a one-dimensional histogram. `Slice1`,
`Slice2`, etc. annotations record exact variable names and bounds, with
zero-based bin indices in paths. Metadata records the beam, frame, target,
density axes and weighting. The YAML used at startup is embedded verbatim as
comments for provenance.

Raw `counts_*` store `sum(w*n)` in `sumw` and `sum((w*n)^2)` in `sumw2`.
`DIS` stores `sum(w)` and `sum(w^2)`; `numEntries` is the eligible event count
in both. Weighted runs additionally write `sum_w2_n_*` with `sum(w^2*n)` in
`sumw`, preserving the mixed moment required to recompute errors after merging
raw accumulators. Normalized histograms store the squared standard error in
`sumw2`. Recompute normalized results after merging raw accumulators; adding
normalized histogram values does not combine independent runs correctly.
The repeated DIS bins are normalization counters, so summing them across
hadron bins does not give a total DIS-event count.

The first axis retains underflow and overflow. Flow multiplicities divide by
finite slice widths but have no first-axis density factor. Particles outside
any secondary axis are excluded and reported in `OutsideSliceRange`; that
counter also includes non-finite axis values. Profiles use the same flow
convention. Reorder axes if a different variable's flow needs inspection.

To obtain `R_A`, divide matching target and deuterium `multiplicity_*` bins
using the same YAML definition. For broadening, subtract matching `pT2`
profile means. These cross-sample operations are downstream; one analyzer
invocation does not load a reference target. Existing plotting helpers that
require `HERMES_2007_FIG2_V1` annotations continue to consume legacy outputs;
they intentionally do not accept the new `YAML_V1_*` selection automatically.

The error estimate assumes independent input event blocks. Multiple SMASH
replicas of one hard event remain correlated and require downstream grouped
uncertainty analysis. Cross-bin covariance is not produced.

## Mean-value and time profiles

`kind: profile` writes native YODA `Profile1D` moments. `quantity` may be any
kinematic variable above, or `prod_time`, `form_time`, or
`formation_interval` (`form_time - prod_time`). The mean pools selected hadrons,
with unit or metadata event weight on each hadron; it is not a mean of
event-level means. Profile errors use native YODA pooled-profile statistics.

Time profiles require named `prod_time`, `form_time`, and `prod_time_status`
columns and accept only status `1`, retaining genuine zero and negative times.
Unavailable/status-0 and spectator/status-2 references are excluded. Missing
time columns leave time profiles empty and increment `MissingTimeEvents`;
other histograms remain available. Non-finite available times are errors.

These are the stored OSCAR **coordinate times**, in fm/c, in the stored OSCAR
frame. Selecting `frame: TRF` or `BREIT` transforms momentum observables only;
it does not transform these times or turn them into proper times. The input
does not contain the complete production four-vertex needed for that operation.
See the [unit conventions](../_generated/units.md).

## Experiment starting configurations

`analysis/configs/` contains `hermes_2007_analysis_input.yaml`,
`hermes_2011_analysis_input.yaml`, `hermes_2012_analysis_input.yaml`,
`clas_2021_analysis_input.yaml`, and separate `emc_100`, `emc_120`, `emc_200`,
and `emc_280` configurations. They transcribe the supplied fixed-target cut
table, omit unspecified cuts, and use **no angular acceptance**. They do not
claim a complete reproduction of each publication's correction procedure.

The HERMES 2007 configuration supplies the existing Fig. 2 `zh`, `nu`, and `Q2`
edges, the distribution-specific `nu` and `zh` selections, and examples of
custom three-dimensional bins and profiles. It applies the table's explicit
`xB` and upper-`nu` bounds, unlike the historical hard-coded event selection.
It excludes neutral pions as requested. The CLAS configuration additionally
defines `zh_Q2_nu` with the exact z, Q2, and nu edges of Tables III–VIII in
[arXiv:2109.09951v2](https://arxiv.org/abs/2109.09951v2). This supplies the
slice histograms needed by the [CLAS Fig. 2/3 plotting script](https://github.com/jordissm/electra/blob/main/analysis/scripts/README.md).
Its existing inclusive histograms, the other experiment configurations, and
custom HERMES histograms use illustrative research binning, which should be
replaced when comparing a particular published table.

EMC energies are kept separate. Reproducing the published combinations needs
the corresponding sample weights or luminosity information; arbitrary generated
sample sizes do not define that experimental combination. The YAML beam
settings do not retune or validate the generated beam energy. Supply matching
simulated samples and preserve the event weights appropriate to those samples.

## Validation

From the repository root, with CMake and a C++17 compiler:

```bash
python3 -m unittest discover -s utils/tests
```

The integration checks use hand-written OSCAR/metadata fixtures and verify
multidimensional denominators, variable-width densities, event-count errors,
weights, cut overrides, profiles, configuration errors, input protection, and
SLURM forwarding. They also retain the legacy analyzer checks.
