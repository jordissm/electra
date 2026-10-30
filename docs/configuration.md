# Configuration

## Experiment settings

Keep these three settings files together under
`input/ehijing/experiments/<experiment>/`:

| File | Role |
| --- | --- |
| `hard_process.setting` | PYTHIA hard process, beams and shower settings |
| `hadronization.setting` | Dedicated hadronizer and vertex diagnostics |
| `dis_cuts.setting` | Reconstructed DIS event-selection cuts |

The Python CLI requires all three paths explicitly. The SLURM script resolves
them from `EXPERIMENT`. Relative paths are resolved from the working directory.

The supplied bundles are:

| Directory / SLURM `EXPERIMENT` | Incoming lepton (`Beams:idB`) | Beam energy (`Beams:eB`, GeV) |
| --- | --- | --- |
| `clas` | Electron (`11`) | 5.014 |
| `hermes_2007` | Electron (`11`) | 27.6 |
| `hermes_2011` | Electron (`11`) | 27.6 |
| `hermes_2012` | Electron (`11`) | 27.6 |
| `emc_Ebeam-100` | Muon (`13`) | 100 |
| `emc_Ebeam-120` | Muon (`13`) | 120 |
| `emc_Ebeam-200` | Muon (`13`) | 200 |
| `emc_Ebeam-280` | Muon (`13`) | 280 |

Use the exact directory name, including the capital `E` in EMC names. The
former `hermes` directory has been replaced by the three year-specific bundles;
select the year for the intended analysis and use all three files from that
bundle. Choosing a bundle sets the beam and generation cuts; target species
and downstream analysis selections are configured separately.

All bundles currently share the same hadronization settings and hard-process
settings apart from the incoming lepton species and energy. They enable
neutral-current photon/Z exchange, disable charged-current exchange, and use
`PhaseSpace:Q2Min = 1.0`. The runtime DIS cuts below are applied separately.

## DIS cuts

The cut loader accepts the optional keys `yMin`, `yMax`, `xBMin`, `xBMax`,
`nuMin`, `nuMax`, `Q2Min`, `Q2Max`, `W2Min` and `W2Max`.
`y` and `xB` are dimensionless, `nu` is in GeV, and `Q2`/`W2` are in GeV².
The configured selections are listed below. Bounds are strict; a dash means
that the corresponding bound is absent from `dis_cuts.setting` and is not
applied by the DIS cut loader. `yMax = 0.85` is set in every bundle.

| Bundle | `Q2Min` | `Q2Max` | `W2Min` | `yMin` | `xBMin` | `xBMax` | `nuMin` | `nuMax` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `clas` | 1.0 | 4.1 | 4.0 | — | — | — | 2.20 | 4.25 |
| `hermes_2007` | 1.0 | — | 4.0 | — | — | — | 4.0 | 23.5 |
| `hermes_2011` | 1.0 | — | 4.0 | — | 0.023 | 0.8 | 6.0 | 23.5 |
| `hermes_2012` | 1.0 | — | 10.0 | 0.10 | 0.023 | 0.6 | — | — |
| `emc_Ebeam-100` | 2.0 | — | — | — | 0.02 | — | 10.0 | — |
| `emc_Ebeam-120` | 2.0 | — | — | — | 0.02 | — | 10.0 | — |
| `emc_Ebeam-200` | 2.0 | — | — | — | 0.02 | — | 30.0 | — |
| `emc_Ebeam-280` | 5.0 | — | — | — | 0.02 | — | 50.0 | — |

No supplied bundle sets `W2Max`. For example, the HERMES 2007 file is:

```{literalinclude} ../input/ehijing/experiments/hermes_2007/dis_cuts.setting
:language: text
```

These generation cuts do not configure detector acceptance or hadron cuts in
the analyzer. Select the appropriate [YAML analysis configuration](analysis/yaml-oscar.md)
separately.

## Runtime controls

The [CLI reference](reference/cli.md) is generated from the current Python
argument parser. The wrapper forwards event counts, IDs, seeds, medium mode,
`K`, target species, tabulation directory and the three settings paths to eHIJING.

ELECTRA defaults to **Generalized Higher Twist (GHT)**, medium modification
mode `1`, in the Python CLI, all supplied hard-process settings, and the SLURM
generation script. Use `--medium-modification-mode 0` locally or
`MED_MODIF_MODE=0` on SLURM to select Higher Twist (HT). The executable's
command-line mode overrides `eHIJING:MediumModificationSplittingFunctionMode`
in the settings file, so choose the runtime option when changing models.
The eHIJING implementation and its internal defaults are unchanged.

`--seed` is an unsigned 64-bit ELECTRA master seed, from `0` through
`18446744073709551615`. The Python defaults are `12345` for generation and
`98765` for transport. The wrapper passes the generation master unchanged;
eHIJING derives separate engine seeds from the master and chunk starting ID.
PYTHIA receives values in `[1, 900000000]` and other engines receive explicit
seeds. Master zero is deterministic and does not select PYTHIA's time-based seed.

The driver and hadronizer override `Random:setSeed` and `Random:seed` after
reading their respective settings files. Editing those settings therefore does
not choose the effective seeds; use the CLI master seed. The bundled integration
also sets `eHIJING:SeedContext` and `eHIJING:SeedRole` for the medium streams.
These are internal policy inputs supplied by the application. See the
[seed policy and stream inventory](_generated/reproducibility.md) and the
[resume contract](running/local.md#reproducibility-and-resuming).

`--history`, `--nuclear-target`, `--nucleon-width-fm`, `--nuclear-radius-fm`
and `--nuclear-surface-fm` are forwarded only when explicitly supplied.
Omitting them leaves the executable's defaults in force, including when using
an older executable. The current nuclear-target implementation and supported
geometry parameters are documented in [shared nuclear target and recoil](_generated/nuclear-target.md).

## Woods–Saxon parameter database

[`input/ehijing/woods_saxon.yaml`](../input/ehijing/woods_saxon.yaml) contains
nucleus entries for the CLAS, EMC and HERMES comparisons, including deuterium
(`d`). Each species has its own
`nucleon_width_fm`, alongside A, Z and its distribution parameters.
Deuterium uses Hulthén sampling; the other entries use Woods–Saxon sampling.

The companion [database notes](../input/ehijing/woods_saxon.md) describe the
fields, units, source references, estimates, isotope choices and local/SLURM
usage. Select an entry with `--nucleus C12` on `ehijing` or
`electra ehijing run`; the executable loads its A, Z and geometry parameters.
`--nucleus-database PATH` selects a custom YAML file. Otherwise, lookup uses
`ELECTRA_NUCLEUS_DATABASE`, the working directory's `input/ehijing/woods_saxon.yaml`,
the executable's adjacent `../share/electra/ehijing/woods_saxon.yaml`, and the
source/build-time installation paths, in that order. Explicit geometry flags
override the YAML values. A missing file, unknown name or invalid entry fails
before generation. Use `ehijing --nucleus C12 --describe-nucleus` to inspect the
resolved parameters as JSON without initializing the generator.

SLURM accepts `NUCLEUS=C12` and optional `NUCLEUS_DATABASE=PATH`. Existing
`--Z`/`--A` callers remain supported, but cannot be combined with `--nucleus`.
Named-target run metadata and Python resume provenance record the resolved
parameters and database SHA-256; changing the database prevents silently
resuming an existing chunk.

## SMASH formation times

The modified SMASH fork defaults to `OSCAR` mode in List and ListBox input:
it uses the Lund-based `prod_time` and `form_time` coordinate times supplied by
eHIJING, in fm/c. The bundled `input/smash/config_files/config.yaml` omits the
formation-time section and uses this default implicitly. Both columns remain
required; missing times cause an error rather than selecting another model.

To select the secondary constant proper-time mode, add this section to a
working copy of the SMASH configuration:

```yaml
Collision_Term:
    Cross_Section_Formation_Scaling:
        Formation_Time:
            Mode: Constant_Proper_Time
            Proper_Time: 1.0  # fm/c; finite and non-negative
```

This keeps the OSCAR production time and sets
`t_form = t_prod + (E/m) * Proper_Time`, using SMASH's validated energy and
effective mass. `Proper_Time` defaults to 1.0 fm/c. `prod_time_status=2`
marks pre-existing spectators: both endpoints equal their production time,
so they remain fully formed. Status 0 retains the warning and zero production
time fallback; status 1 uses the supplied production time, including zero.
Imported positions and trajectories are unchanged.

Keep the full `Optional_Quantities` list for current eHIJING files. Constant
mode reads and ignores `form_time`; omit it from the configuration only if
the corresponding column is also absent from the input file. Files without
`prod_time_status` cannot identify the spectator exemption.

To select the Lund-based times explicitly, set `Formation_Time.Mode: OSCAR`
under the same parent section; `Proper_Time` has no effect in that mode.
`Profile.Path` controls the cross-section shape independently of the timing
mode. The old custom `Profile.Formation_Time` option is replaced by the
`Formation_Time` section above. Stock SMASH option names are unchanged.
Rebuild SMASH or the container before using the new options. Both local and
SLURM workflows use the implicit `OSCAR` default with the bundled config.

## Diagnostics

HepMC histories use the runtime flag `--history on`. Fragmentation tracing
is independently enabled in the hadronization settings:

```text
HadronVertex:trace = on
Fragmentation:setVertices = on
HadronVertex:mode = 2
```

Read [history records](_generated/history.md),
[fragmentation traces](_generated/fragmentation.md) and
[unit conventions](_generated/units.md) for their different coordinate orders,
units, frames and limitations. Rebuild the executable and bundled PYTHIA, and
update the container/SIF, when adopting changes to these interfaces.
