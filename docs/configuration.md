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

## DIS cuts

The cut loader accepts the optional keys `yMin`, `yMax`, `xBMin`, `xBMax`,
`nuMin`, `nuMax`, `Q2Min`, `Q2Max`, `W2Min` and `W2Max`.
`y` and `xB` are dimensionless, `nu` is in GeV, and `Q2`/`W2` are in GeV².
The supplied HERMES file is:

```{literalinclude} ../input/ehijing/experiments/hermes/dis_cuts.setting
:language: text
```

## Runtime controls

The [CLI reference](reference/cli.md) is generated from the current Python
argument parser. The wrapper forwards event counts, IDs, seeds, medium mode,
`K`, target species, tabulation directory and the three settings paths to eHIJING.

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
