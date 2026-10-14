# ELECTRA

ELECTRA (ELectron-ion Event generation Coupled to TRAnsport) combines eHIJING
event generation with SMASH hadronic transport for electron-ion collision studies.
The Python CLI connects the stages; containers package the physics dependencies
and utilities for local and SLURM execution.

Start with [installation](getting-started.md), then follow the
[local workflow](running/local.md) or [SLURM workflow](running/slurm.md).
Consult the physics and interface pages before interpreting spacetime diagnostics.

```{toctree}
:maxdepth: 2
:caption: User guide

getting-started
running/local
running/slurm
configuration
outputs
analysis/fragmentation
analysis/rivet
```

```{toctree}
:maxdepth: 2
:caption: Physics and interfaces

_generated/physics-tutorial
_generated/ehijing
_generated/assumptions
_generated/reproducibility
_generated/nuclear-target
_generated/units
_generated/history
_generated/fragmentation
```

```{toctree}
:maxdepth: 1
:caption: Development and reference

development/architecture
development/documentation
reference/cli
reference/python-api
_generated/cpp-api
```

The component physics pages are adapted at build time from the eHIJING checkout;
CI tracks eHIJING's `main` branch using `docs/ehijing-revision.txt`.
The [eHIJING paper](https://doi.org/10.1103/PhysRevD.110.034001) describes
the event-generation model. See the [SMASH documentation](https://smash-transport.github.io/)
for its upstream transport model and configuration.
