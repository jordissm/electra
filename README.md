
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

This saves `event_00000000.pdf` with a lab-frame event overview, per-string
lab and input-rest-frame diagrams, longitudinal Lund reference pages, and final
particle-time tables. A multi-string overview has no unique string rest frame
and stays in the lab; each individual string gets its own CM view when its
recorded momentum is timelike. The container includes the script at
`/opt/electra/share/utils/plot_fragmentation.py`.

**Lund boundaries are enabled on the first overview and saved-vertex pages**,
including `--overview-only`. Bold solid lines show original endpoint boundaries,
thin lines show breakup constituents, and verified reference string area is
shaded. Filled green/purple circles show stored pair-creation/formation vertices;
boundary turns remain as bends in the curves without separate markers or
labels. Hollow `RB`/`RF` circles show converted reference breakups/meetings.
The primary
vertex is a yellow star. Reference and saved formation points can differ because
Pythia's late prescription uses the full hadron momentum, including transverse
fragmentation momentum even when vertex smearing is off.

Each reference string/leg uses its recorded inherited origin, not an average of
input endpoint birth events. Gluon bases are normalized to the same half-gluon
momenta used by the region offsets before stitching. Spacetime conversion
corrections are included; unverified paths and worldsheet fill are omitted.
`B!` marks a converted breakup outside the reference domain; `H!` marks a saved
lab-frame formation earlier than an associated breakup. These assignments
cannot be interpreted as a complete causal classical constituent history.

One-hadron collapses default to **both the effective Lund diamond and the
massive input endpoint curves** (`--collapse-model both`), including on their
dedicated rest-frame pages. The diamond uses dash-dot boundaries; the input
curves are dotted. The final
hadron momentum after recoil exchange and recorded origin define a massless
model closing at the assigned late point `F = O + p_h/kappa`. Its axis follows
the positive input endpoint direction in the final hadron rest frame. Model
turns are retained in the curves without markers or labels. This is an
effective post-collapse picture, not the massive pre-collapse recoil history.
It is used when the stored assignment satisfies that late formula (unsmeared
light-flavour mode 2); otherwise the available input endpoint model is retained.

Use `--collapse-model effective` or `--collapse-model input` to show only one
collapse model. The massive pre-collapse endpoint diagnostic uses the input
partons rather than the post-recoil hadron.
Those constant-force curves stop after the first outward-and-return excursion,
with input-CM duration `2*abs(p_parallel)/kappa`. Their distinct recorded starting
vertices are retained. They exclude fragmentation and recoil exchange and are
not fitted to the formation point. For this model, gluon kinks and junctions
are unsupported. The equation of motion is
[Eq. (17) of Ferreres-Sole and Sjostrand](https://arxiv.org/html/1808.04619v2#S2.SS2.SSS5).

The hollow diamonds mark recorded input constituent starting vertices. A turning
point on either model's boundary does not create a constituent. The effective diamond's
common origin is an inherited model anchor; the purple point is the assigned
**hadron** formation. The two models do not record the intervening recoil history.

Main plots of an event share axis limits within each frame/spatial projection.
The default longitudinal pages also share numerical ranges across all strings,
although each uses a different string rest frame and axis; this is a comparison
of scales, not a common spacetime coordinate system. Endpoint-detail insets
retain their local zoom. Reference projection pages use the same frame origin
and boost as the corresponding saved-vertex pages.

Useful options:

- `--string 0 --pass 1`: select one string.
- `--frame lab --overview-only`: all selected strings in one common lab frame.
- `--frame both` (default): lab and each individual input string's CM plots and tables.
- `--frame lab`: lab plots and tables only, unless a rest-frame `--lund-view` is explicitly requested.
- `--frame string-rest`: individual input-string CM plots and tables; a multi-string overview still uses lab.
- `--lund-view projection`: reference pages in the chosen `--frame`/`--axis`;
  otherwise their own CM longitudinal axis is used. Collapse pages use the final
  hadron rest frame.
- `--axis x`, `--axis y`, `--no-labels`, `-o output.pdf`.
- `--no-table`: omit final tables; `--overview-only` omits per-string pages and tables.

Tables show recorded `prod_time` and one `form_time` in mode 2. Formation time
uses the final particle record when available, otherwise the fragmentation
assignment. Rest-frame production time is recomputed from the full production
references; scalar lab times are not boosted. Rest tables use the input string CM
and primary origin, matching saved-vertex plots; effective diamond pages use
the final hadron CM and inherited origin.
The rest-frame table collects rows from different strings on the same page,
with each row evaluated in its own input string CM, rather than assigning a
common rest frame to the multi-string event.

In mode 2, the first and last hadrons of an ordinary open string use its inherited
origin in place of the endpoint turn when selecting the earlier production
reference. The geometric turns are retained for the boundary paths and unchanged
late formation calculation. Interior hadrons still use their two breakup points;
two-hadron mini-strings, closed strings and junctions keep their existing rules.
Single-hadron collapses use the inherited collapse origin directly for production,
without constructing a breakup pair. Rebuild PYTHIA/eHIJING and regenerate events
to apply these assignments; older traces retain their historical production times.

- `--duration 5`: extend free hadron worldlines by 5 fm/c beyond the latest
  formation. This does not set constituent trajectory lengths.
- `--no-lund-boundaries`: omit the overlay on overview/saved-vertex pages.

Version 4 traces include converted `REFERENCE_BREAKUP` points and explicit
inherited origins. Older v2/v3 traces remain readable; unsmeared light-flavour
breakup pairs supply converted points where possible. Rebuild Pythia/eHIJING
and the container, then regenerate events to use the native recoil-vertex fix
and the common inherited origin for two-hadron mini-strings. Existing traces
retain their historical saved metadata; the plotter does not rewrite it.

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
