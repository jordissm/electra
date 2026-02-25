
# ELECTRA Framework (ELectron-ion Event Collision TRAnsport)

Simulation framework designed specifically for modeling electron-ion collision events. Leveraging eHIJING for initial collision event generation and [SMASH](https://smash-transport.github.io) for subsequent hadronic transport. For physics details, please refer to [arXiv:2501:XXXXX](https://www.arxiv.org/abs/2501.XXXXX).

## Overview

This repository provides a framework to simulate electron-ion collision events from the initial hard scattering process through eHIJING, through the time-dependent hadronization process, and final hadronic transport and decay via [SMASH](https://smash-transport.github.io). The results can be used to predict, compare, and contrast to observations from experiments at the Electron-Ion Collider (EIC).

## Features

- *Event generation with eHIJING:*
- *Hadronic transport with SMASH:*
- *Modular design:*

## Installation

### Prerequisites

- C++17 compatible compiler (GCC, Clang)
- ROOT libraries

### Quick Start

1. Clone the repository:

2. Build:

## Usage

'''
docker buildx build --platform=linux/amd64 --load -t electra:latest -f Dockerfile .
'''

'''
 docker run -it --name electra --platform=linux/amd64 --mount type=bind,source=$PWD,target=/SMASH/mnt electra:latest
'''

'''
docker start -ai electra
'''

'''
./smash -i /SMASH/mnt/input/config_pp.yaml -o /SMASH/mnt/output/smash/pp_0d0
'''

'''
python3 shard_profiles.py --in-dir input/smash/xsec_scaling_factor_profiles/ --out-root run/profiles --out-index run/profiles/profiles.jsonl --mode copy
'''

## Citation

If you use ELECTRA in your research, please cite:

```bibtex
@article{salinassanmartin2025electra,
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

## Acknowledgements

This work has been supported by the Saturated Glue (SURGE) Topical Theory Collaboration.
