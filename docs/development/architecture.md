# Architecture and validation

## Components

| Path | Responsibility |
| --- | --- |
| `python/electra/` | Orchestration CLI, paths, task selection and seeds |
| `src/ehijing/` | Separate C++ application checkout and modified PYTHIA |
| `src/smash/` | Separate modified SMASH checkout |
| `input/` | Simulation settings and reference inputs |
| `utils/` | Conversion, event processing and plotting |
| `rivet-analyses/` | Rivet plugins and analysis scripts |
| `slurm-scripts/` | Cluster resource configuration and submissions |
| `containers/Docker/` | Packaged dependency and application builds |

The event-generation sequence is described in the
[eHIJING component overview](../_generated/ehijing.md). The Python wrapper
invokes eHIJING for event chunks and SMASH for event/profile pairs. Files and
completion markers record progress. The wrapper passes the master seed
unchanged to eHIJING, whose versioned policy derives chunk and engine streams;
Python derives SMASH's event/profile seed using canonical JSON and SHA-256.
Completed requests are skipped only after saved seed, settings and executable
fingerprints match. eHIJING also checks table digests; SMASH checks event/profile
bytes and replica count. Historical markers without provenance and changed
requests require a new run directory. See the
[seed and replay contract](../_generated/reproducibility.md).

## C++ builds

The eHIJING application uses CMake and requires PYTHIA, HepMC3 and GSL.
Use a configured dependency installation or the container recipe for a full
application build. Its documentation-only target avoids these dependencies:

```bash
cmake -S src/ehijing -B /tmp/electra-build-docs -DEHIJING_BUILD_DOCS_ONLY=ON
cmake --build /tmp/electra-build-docs --target docs
```

This produces the component's standalone Doxygen HTML, with Doxygen installed
and Graphviz recommended. The Sphinx build can instead embed Doxygen XML
through Breathe; see [documentation builds](documentation.md).

The seed policy requires rebuilding both eHIJING and the bundled modified
PYTHIA library/XML settings, then updating the container/SIF. The new policy
changes historical samples; retain their original binaries and records for
replay. Fingerprints do not capture every shared library or runtime setting.

## Focused checks

With an eHIJING application build configured with `BUILD_TESTING=ON`:

```bash
ctest --test-dir /path/to/ehijing-build --output-on-failure
```

Synthetic tests cover seed derivation, diagnostic history, target geometry,
recoil and spectator bookkeeping. They do not replace physics validation with a
production sample.
Use focused checks for the component you change; routine documentation work
does not require event generation or container image publication.

Python seed forwarding and resume checks run without simulations:

```bash
PYTHONPATH=python python3 -m unittest discover -s tests -v
```

Full replay smoke checks use temporary outputs and are opt-in; see the
[local workflow](../running/local.md#reproducibility-and-resuming).

For physics or spacetime changes, preserve the
[unit and frame conventions](../_generated/units.md), and update the relevant
interface documentation together with the code.
