
# ELECTRA Framework (ELectron-ion Event Collision TRAnsport)

Simulation framework designed specifically for modeling electron-ion collision events. Leveraging [eHIJING](https://doi.org/10.1103/PhysRevD.110.034001) for initial collision event generation and [SMASH](https://smash-transport.github.io) for subsequent hadronic transport. For physics details, please refer to [arXiv:2601:XXXXX](https://www.arxiv.org/abs/2601.XXXXX).

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
