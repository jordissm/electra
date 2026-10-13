
# ELECTRA ⚡️

<p align="center">
<img src="utils/banner.png" alt="banner" width="550"/>
</p>

(ELectron-ion Event Collision TRAnsport) simulation framework designed specifically for modeling electron-ion collision events. Leveraging [eHIJING](https://doi.org/10.1103/PhysRevD.110.034001) for initial collision event generation and [SMASH](https://smash-transport.github.io) for subsequent hadronic transport. For physics details, please refer to [arXiv:2601:XXXXX](https://www.arxiv.org/abs/2601.XXXXX).

## Overview

This repository provides a framework to simulate electron-ion collision events from the initial hard scattering process through [eHIJING](https://doi.org/10.1103/PhysRevD.110.034001), through the time-dependent hadronization process, and final hadronic transport and decay via [SMASH](https://smash-transport.github.io). The results can be used to predict, compare, and contrast to observations from experiments at the Electron-Ion Collider (EIC).

## Features

- *Event generation with eHIJING:* Medium-modified QCD splitting functions within the higher-twist (HT) and generalized higher-twist (GHT) frameworks are utilized to simulate parton showering in the nuclear medium that takes into account the non-Abelian Landau-Pomeranchuck-Midgal interference effect.
- *Hadronic transport with SMASH:* Hadronic interaction between jet and nucleus are handled utilizing SMASH with custom cross section scaling factors depending on formation time.
- *Modular design:* A flexible pipeline that allows to access intermediate output files.
- *Containerized deployment:* Dependencies and utilities, as well as the orchestrator scripts are shipped on a Docker/Apptainer container to bypass installation steps and guarantee reproducibility.
- *Continous Integration / Continous Delivery (CI/CD):* Container images are built pushed to the registry after every commit, facilitating access to the newest stable version.

## Quick Start

### SLURM cluster execution

1. Download and execute the `install.sh` script:

```terminal
curl -fsSL https://raw.githubusercontent.com/jordissm/electra/main/install.sh -o install.sh \
  && chmod +x install.sh \
  && ./install.sh --pull-sif
```

1. Execute `ehijing` using the SLURM script provided:

```terminal
bash slurm-scripts/ehijing_submit.sh NEVENTS=<NEVENTS> CHUNK_SIZE=<CHUNK_SIZE>
```

where `<NEVENTS>` should be an integer between `1` and `1_000_000` and `<CHUNK_SIZE>` should be an integer between `1` and `<NEVENTS>`.

1. Execute `smash` using the SLURM script provided:

```terminal
bash slurm-scripts/smash_submit.sh NEVENTS=<NEVENTS> CHUNK_SIZE=<CHUNK_SIZE>
```

where `<NEVENTS>` need to match the same number used for eHIJING but `<CHUNK_SIZE>` needs not.

### Local execution

1. Download and execute the `install.sh` script:

```terminal
curl -fsSL https://raw.githubusercontent.com/jordissm/electra/main/install.sh -o install.sh \
  && chmod +x install.sh \
  && ./install.sh
```

## Usage

The installer copies packaged utilities into `<prefix>/utils` on both local and
cluster installs. Use `--utils <dir>` to choose another directory. Re-running
the installer adds missing files and preserves existing utility files.

### Hadronization spacetime diagrams

Enable the following in the eHIJING hadronization configuration:

```text
HadronVertex:trace = on
Fragmentation:setVertices = on
HadronVertex:mode = 2
```

Each `event_XXXXXXXX.oscar` then gets a matching `event_XXXXXXXX.fragmentation`
file with string membership, partons, breakup vertices, saved formation points,
production times and the final particle record. Both files share the event's
shard directory. Rebuild eHIJING/PYTHIA and the container to use this feature.

Plot one trace with Python 3.10+ and matplotlib:

```bash
python3 utils/plot_fragmentation.py /path/to/event_00000000.fragmentation
```

This saves `event_00000000.pdf` with saved vertices, massive input endpoint curves and outgoing hadron worldlines,
diagrams for each string/pass, longitudinal Lund constituent pages for v3
records, and hadron time tables. Breakups are solid green circles, formations
solid purple circles, and the primary vertex a yellow star. Options include
`--axis x`, `--axis y`, `--string 0 --pass 1`, `--frame string-rest`,
`--duration 5`, `--no-labels`, `--overview-only`, and `-o output.pdf`.
The container includes the utility at `/opt/electra/share/utils/plot_fragmentation.py`.
**Lund boundaries are enabled by default on the first overview and saved-vertex
pages, including with `--overview-only`.** Bold solid lines show original
endpoints, thin solid lines show breakup constituents, and shading shows the
surviving reference string. Filled circles retain the recorded breakup and
formation vertices; hollow `RB`/`RF` circles identify reference breakups and
meetings. Use `--no-lund-boundaries` to omit this overlay from those pages.
`--lund-boundaries` explicitly enables it; no extra option is needed normally.
Hadron worldlines use `dx/dt = p/E` from saved formation points before OSCAR
smearing. The Lund pages show bold original endpoint boundaries, thin
constituent boundaries from each breakup, and a shaded surviving string
worldsheet. By default each page uses that string's rest frame with the spatial
axis aligned with its recorded positive light-cone direction. This gives the usual Lund
opening arms and fragmented string regions. Use `--lund-view projection` for
these pages in the selected `--frame` and `--axis` instead.
These pages use the longitudinal massless-reference picture, excluding
transverse tunnelling/smearing and heavy-endpoint corrections; their formation
points can differ from the saved vertices. Shading removes the future of every
pair-creation breakup; incomplete breakup coordinates suppress the shading.
Original outward endpoint arms are reconstructed independently of the hadron
solutions, so a missing final-two path does not hide an otherwise recorded arm.
One-hadron collapses have no recorded parameter plane and retain the separate
massive-endpoint model on their saved-vertex pages.
For groups without both connected reference endpoint boundaries, the
saved-vertex pages show the massive original endpoint model for two-parton
open strings, including one-hadron collapses. Dash-dot curves use the input
momenta, masses and recorded starting vertices with a constant force
`dp_parallel/dt = +/- kappa` in the input string rest frame, then boost back
to the selected plot frame. Diamonds mark recorded starts and triangles model
turns. Each curve stops after its first outward-and-return excursion.
Individual string pages add a close-up when endpoint motion is small compared
with the formation-time scale; labels are spaced to avoid overlapping.
This is an unbroken-string reconstruction, not a recorded PYTHIA history:
pair creation and collapse recoil exchange are excluded, and curves are not
forced to meet at saved formation points. Distinct endpoint birth vertices
are retained; assuming a separate force clock at each birth is a diagnostic
approximation. Gluon kinks, junctions and invalid/missing inputs are reported
as unsupported for this massive model. Old v2/v3 files with parton momenta
already support it; new traces additionally record endpoint masses explicitly.

The separate massless-reference pages use one shared mean endpoint vertex
(or mean leg origin) per string/leg, so adjacent paths join. This is a plotting
anchor, not a change to saved vertices. Regenerate v2 traces after rebuilding
eHIJING/PYTHIA for the parameter-plane paths of newly created constituents.
The massive model follows the straight-string equation of motion in
[Ferreres-Solé and Sjöstrand, Eq. (17)](https://arxiv.org/html/1808.04619v2#S2.SS2.SSS5).

## Citation

If you use ELECTRA in your research, please cite:

```bibtex
@article{salinassanmartin2026electra,
    title={},
    author={},
    journal={},
    volume={},
    pages={},
    year={2025}
}
```

## License

ELECTRA is released under the UIUC License. See [LICENSE](LICENSE) for details.

## Attribution

This project is the collaboration of J. Salinas San Martin, W. Zhao, W. Ke, J. Noronha-Hostler, and X.-N. Yang.

## Acknowledgements

This work has been supported by the Saturated Glue (SURGE) Topical Theory Collaboration.
