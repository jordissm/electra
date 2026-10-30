# Plotting scripts

Choose the experiment first, then the comparison and observable:

```text
HERMES/
  hermes2007.py                       HERMES Fig. 2 selection/count reader
  plot_hermes_fig2.py                 z_h, nu and Q2 comparisons
  cross_section_profile_comparison/
    R_A/                             nuclear multiplicity ratios and poster
    e_d/                             deuterium spectra
  model_comparison/
    R_A/                             nuclear multiplicity ratios
    e_d/                             deuterium spectra
CLAS/
  clas2021.py                         CLAS YAML multiplicity reader
  cross_section_profile_comparison/
    R_A/                             charged-pion ratios versus z_h, inclusive and Q2/nu binned
EMC/
  emc1991.py                         single-energy EMC charged-hadron multiplicity reader
  cross_section_profile_comparison/
    R_A/                             EMC Fig. 4 / eHIJING Fig. 18, C/Cu/Sn
experiment_comparison/
  hadronization_comparison/
    times_vs_zh/                     HERMES, EMC and CLAS time profiles
```

The existing `analysis/run_HERMES_*.sh` and
`analysis/run_hadronization_comparison_times_vs_zh.sh` launchers retain their
names and arguments. Direct Python paths now include the experiment directory.
The time comparison uses multiple experiments, so it lives under
`experiment_comparison/`. Its present HERMES selection is described in the
[time analysis guide](../../docs/analysis/times-vs-zh.md).
Data and output locations remain under `analysis/experimental_data/` and
`analysis/output/<EXPERIMENT>/`. Input paths in plot configs resolve relative
to the config file, independently of the working directory.

## Run every plotting workflow

From the repository root:

```bash
bash analysis/run_all_plot_scripts.sh
```

The runner invokes all four HERMES model/profile workflows (including the
poster and Fig. 2 plots), all three CLAS pion figures, the EMC comparison, and the configured time
comparison. It continues after errors and exits with status 1 if any workflow
fails, listing the failed workflows at the end. Existing launchers retain
their output directories. The time comparison writes one panel containing
production and formation curves for CLAS, HERMES, and EMC to
`analysis/output/plots/experiment_comparison/times_vs_zh/`. Run it on its own
with `bash analysis/run_hadronization_comparison_times_vs_zh.sh`; it uses the
same input and output defaults as the all-plots runner.

The CLAS workflow uses its supplied `RA_vs_zh_inputs.yaml` by default and
requires the configured simulation files. Use `--clas-data-only` to plot the
published data when those inputs are unavailable, or `--clas-config FILE`
to select another profile config. The time comparison uses the local
`times_vs_zh_inputs.json` if present, otherwise the three-experiment example;
`--times-config FILE` selects a different set of samples and
`--times-output-dir DIR` changes its figure destination. Paths provided on
the command line resolve relative to your working directory.

Use `--dry-run` to inspect all seven commands without creating figures or
`--help` for the options. Set `PYTHON=/path/to/python` to select an interpreter
with Matplotlib. The runner reads existing analysis outputs; it does not
generate simulation events.

The EMC workflow reads `analysis/experimental_data/EMC/R_A/Fig4.csv`, which
is pending the original experimental table. Use `--emc-data-file FILE` to
select another CSV, `--emc-config FILE` to select simulation profiles, or
`--emc-data-only` to omit simulation overlays. Missing measurements produce
an explicit error and are included in the runner's failure summary.

## CLAS Fig. 1

With Python 3.10+ and Matplotlib, run from the repository root:

```bash
bash analysis/run_CLAS_cross_section_profile_comparison_plot_scripts_R_A.sh
```

The CLAS launcher writes `RA_vs_zh.pdf` and `RA_vs_zh.png` plus the two binned
figures described below to
`analysis/output/CLAS/cross_section_profile_comparison/R_A/`. Use `--output-dir`
and `--output-filename` to choose another destination. The experimental points
come from [Table II of arXiv:2109.09951v2](https://arxiv.org/abs/2109.09951v2),
stored in `analysis/experimental_data/CLAS/R_A/TableII.csv`. There are ten
positive-pion and eight negative-pion bins for each of C, Fe and Pb. Positions
are bin midpoints because the table supplies bin bounds rather than mean z.

The figure uses the HERMES script's two-row layout (pi+ above pi-), with C, Fe,
and Pb in columns, thin adjoining frames, black markers, statistical error
bars, and gray systematic-error boxes spanning each bin. The paper overlays
both charges in three panels and adds statistical and systematic errors in
quadrature; this script separates them to match the HERMES style.
The legend sits in the pi+/C panel and combines the marker, statistical bar,
and systematic box into one CLAS symbol.

To overlay simulated cross-section profiles:

```bash
bash analysis/run_CLAS_cross_section_profile_comparison_plot_scripts_R_A.sh \
  --config analysis/scripts/CLAS/cross_section_profile_comparison/R_A/RA_vs_zh_inputs.yaml
```

The supplied config matches `profile_XXXXXX.yoda` under
`analysis/output/CLAS/cross_section_profile_comparison/R_A/{d,C,Fe,Pb}/`.
Alternatively, replace `profile_directory` with explicit scenarios:

```json
{
  "scenarios": [
    {
      "label": "My profile",
      "color": "green",
      "linestyle": "-",
      "deuterium": "/path/to/d/profile.yoda",
      "nuclei": {
        "C": "/path/to/C/profile.yoda",
        "Fe": "/path/to/Fe/profile.yoda",
        "Pb": "/path/to/Pb/profile.yoda"
      }
    }
  ]
}
```

JSON configs work without PyYAML; other YAML syntax requires PyYAML.
Profile IDs use the same colors, labels and line styles as the HERMES profile
plot. `--no-errorbars` suppresses simulation bands; `--no-exp` plots only
simulation and requires `--config`. Missing/empty configured inputs or
incompatible histograms are errors.

Use the [configurable analyzer](../../docs/analysis/yaml-oscar.md) to obtain
`/CLAS_2021/zh/multiplicity_pip` and `multiplicity_pim`. The reader divides
normalized, matching target/deuterium bins and propagates their independent
event-level standard errors. It preserves zero nuclear yields, omits undefined
ratios, and rejects different bin edges, beam/frame metadata, or embedded YAML
definitions. It does not interpolate or rebin inputs. Never sum already
normalized multiplicities to merge runs; see the analyzer guide.

The plotter does not apply event cuts or certify that inputs reproduce the
publication. Fig. 1 integrates over 2.20 < nu < 4.25 GeV, 1.0 < Q2 < 4.0 GeV^2,
and pT^2 < 1.5 GeV^2. The existing
`analysis/configs/clas_2021_analysis_input.yaml` is explicitly illustrative:
it uses Q2 < 4.1 GeV^2, uniform z bins, and no angular acceptance. Supply
an analysis definition appropriate to your comparison before interpreting
simulation overlays as a reproduction. This change does not alter those
physics selections or generate events.

## CLAS Figs. 2 and 3: Q2 and nu bins

To generate only the new figures, run:

```bash
python3 analysis/scripts/CLAS/cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py
```

The script writes `RA_vs_zh_binned_Q2_nu_pip.pdf` (Fig. 2, pi+) and
`RA_vs_zh_binned_Q2_nu_pim.pdf` (Fig. 3, pi-), plus PNG copies, alongside the
inclusive plot. It is also included in the CLAS launcher and all-plots runner.
Add `--particles pip` or `--particles pim` when invoking the Python script to
produce one figure. Other shared options such as `--output-dir`, `--no-exp`,
`--no-errorbars`, `--config`, and `--figsize` work as for the inclusive plot.
`--output-filename` sets a prefix with `_pip`/`_pim` appended.

Each figure has C, Fe, and Pb columns and three nu rows: 2.2–3.2, 3.2–3.7,
and 3.7–4.2 GeV. The pion label appears inside the leftmost panel of each row.
Colors/markers identify Q2 intervals 1.0–1.3, 1.3–1.8,
and 1.8–4.1 GeV^2. The top-left panel contains the combined statistical-bar,
systematic-box and marker legend. The data are extracted from Tables III–VIII
of [arXiv:2109.09951v2](https://arxiv.org/abs/2109.09951v2) and stored in
`analysis/experimental_data/CLAS/R_A/TablesIII_VIII.csv`. Blank source entries
remain absent measurements. Points use bin midpoints without horizontal shifts.
Automatic y limits are shared within each row and include the large pi-
high-z uncertainties; `--ylim LOW HIGH` applies fixed limits to every panel.

Simulation overlays use the same profile inputs as the inclusive plot.
Q2 colors distinguish the slices and profile line styles distinguish scenarios;
profile colors are reserved for the inclusive figure. The analyzer config now
includes `zh_Q2_nu` with the exact published edges. Regenerate existing CLAS
YODA files with that config before requesting the new overlays. Required paths
have the form:

```text
/CLAS_2021/zh_Q2_nu/Q2_bin0/nu_bin0/multiplicity_pip
/CLAS_2021/zh_Q2_nu/Q2_bin0/nu_bin0/multiplicity_pim
```

Both indices run from 0 to 2. The reader checks the physical `Slice1`/`Slice2`
bounds as well as matching nuclear/deuterium provenance and z edges. The global
cuts and existing histograms in the analyzer config remain as before; these
new slices end at nu = 4.2 GeV as printed in Tables III–VIII. No angular
acceptance or additional model is introduced.

## EMC Fig. 4 / eHIJING Fig. 18

The EMC plot uses adjoining C, Cu, and Sn panels with the same thin frames,
profile colors/line styles, in-panel h+/- label, and legend in the first panel.
The references are [the EMC publication](https://doi.org/10.1007/BF01412322)
and [eHIJING Fig. 18](https://arxiv.org/abs/2304.10779). Original experimental
values have not been filled in: the empty `Fig4.example.csv` documents the
input schema, and no points digitized from the eHIJING figure are used.

Once the original EMC table is available, run:

```bash
bash analysis/run_EMC_cross_section_profile_comparison_plot_scripts_R_A.sh \
  --data-file /path/to/Fig4.csv
```

This writes PDF and PNG copies of `RA_vs_zh` under
`analysis/output/EMC/cross_section_profile_comparison/R_A/`. Place the table
at `analysis/experimental_data/EMC/R_A/Fig4.csv` to use the default.
The CSV requires `nucleus,z,R`, plus either a single absolute `error` or
separate absolute `stat,sys`. Optional `z_low,z_high` specify bin bounds;
optional `beam_energy` identifies a 100 or 280 GeV sample. Do not infer missing
experimental beam assignments, bin edges, or an uncertainty decomposition.
The script uses quoted z positions directly. It draws systematic boxes when
bin bounds exist and gray vertical systematic bars otherwise. A single quoted
error is shown as one error bar. Statistical and systematic representations
share one EMC legend symbol when both are supplied.

For simulation overlays, pass `--config` with the adjacent
`RA_vs_zh_inputs.yaml`. Discovery expects
`<profile_directory>/{100,280}/{d,C,Cu,Sn}/profile_XXXXXX.yoda`, matching each
available target to deuterium at the same energy and profile ID. Missing
target/energy combinations are not synthesized. Explicit scenarios use:

```json
{
  "scenarios": [
    {
      "label": "My profile",
      "color": "green",
      "linestyle": "-",
      "samples": [
        {
          "nucleus": "Cu",
          "nuclear": "/path/to/Cu/profile.yoda",
          "deuterium": "/path/to/d/profile.yoda"
        }
      ]
    }
  ]
}
```

The existing EMC YAML analyzer configurations provide
`/EMC_100/zh/multiplicity_charged` or `/EMC_280/zh/multiplicity_charged`.
The reader requires matching provenance, bins, beam energy, and a muon beam,
and propagates the analyzer's event-level errors. Each target/deuterium pair
uses one beam energy; 100 and 280 GeV curves are shown separately with circle
and square markers. The plotter does not average energies, choose luminosity
weights, or merge normalized files. The supplied analyzer configurations still
have illustrative binning and omit angular acceptance; match the original
table's selections before interpreting overlays quantitatively. Use `--no-exp`
with `--config` for simulation-only plots, and `--no-errorbars` to hide
simulation bands. Existing research data and analyzer selections are unchanged.
