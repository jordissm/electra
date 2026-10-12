
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

This saves `event_00000000.pdf` with saved vertices and outgoing hadron worldlines,
diagrams for each string/pass, longitudinal Lund constituent pages for v3
records, and hadron time tables. Breakups are solid green circles, formations
solid purple circles, and the primary vertex a yellow star. Options include
`--axis x`, `--axis y`, `--string 0 --pass 1`, `--frame string-rest`,
`--duration 5`, `--no-labels`, `--overview-only`, and `-o output.pdf`.
The container includes the utility at `/opt/electra/share/utils/plot_fragmentation.py`.
Hadron worldlines use `dx/dt = p/E` from saved formation points before OSCAR
smearing. Separate constituent pages use the longitudinal massless-reference
string picture, excluding transverse tunnelling/smearing and heavy-endpoint
corrections; their formation points can differ from the saved vertices.
Regenerate old v2 traces after rebuilding eHIJING/PYTHIA for constituent paths.

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
