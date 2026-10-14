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

`--history`, `--nuclear-target`, `--nucleon-width-fm`, `--nuclear-radius-fm`
and `--nuclear-surface-fm` are forwarded only when explicitly supplied.
Omitting them leaves the executable's defaults in force, including when using
an older executable. The current nuclear-target implementation and supported
geometry parameters are documented in [shared nuclear target and recoil](_generated/nuclear-target.md).

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
