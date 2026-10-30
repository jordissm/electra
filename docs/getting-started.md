# Installation

Use the packaged container to run ELECTRA without building the physics
dependencies locally. Docker is used for local execution; SLURM scripts use
Apptainer and a SIF image. Python utilities require Python 3.10 or newer.
The installer builds the standalone OSCAR analyzer on the host, requiring
CMake and a C++17 compiler. Its build script downloads and verifies yaml-cpp
0.8.0 and installs a private static library in the analysis build directory.
The first build needs internet access unless a local source archive or an
existing yaml-cpp installation is supplied.

## Local installation

From the repository root, with Docker available:

```bash
bash install.sh
./electra-shell -- electra --help
```

The installer creates `electra-shell`, prepares input/output directories,
and copies packaged utilities. Existing utility sources are preserved; default
input files are copied only when the input directory is empty. Use
`bash install.sh --help` for paths and image overrides.

It then builds `<prefix>/utils/analyze_oscar_output`, or
`<custom-utils-directory>/analyze_oscar_output` when `--utils` is supplied.
To rebuild after changing the installed C++ sources or headers, run:

```bash
bash /absolute/path/to/install/utils/build_analysis.sh --jobs 2
```

The script resolves its own source directory and keeps incremental CMake
build files under `<utils-directory>/build/analysis`. It replaces the installed
executable only after a successful build. It does not recopy the packaged
sources. Existing source edits are also preserved when the installer is rerun.
Use the actual utility path when `--utils` selects a custom directory.

On a cluster, load CMake and a compiler compatible with the compute nodes
before installing or rebuilding. If build tools are not yet available, use
`bash install.sh --skip-analysis-build`, then run the build script later.
The installer prints the executable and rebuild-script locations.

On a cluster without internet access, provide either the official source
archive or an existing library installation when running the installer:

```bash
ELECTRA_YAML_CPP_ARCHIVE=/absolute/path/to/yaml-cpp-0.8.0.tar.gz bash install.sh
# Alternatively:
ELECTRA_YAML_CPP_PREFIX=/absolute/path/to/yaml-cpp-install bash install.sh
```

The source archive is checked against the pinned SHA-256 before extraction.
After a successful dependency setup, rebuilding reuses its cached source and
installation. No system-wide installation or Docker library is needed by the
default host analyzer build.

For an installation without an existing checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/jordissm/electra/main/install.sh -o install.sh
bash install.sh
```

The default Docker image is `ghcr.io/jordissm/electra:latest`. For reproducible
production, select a specific image tag or digest with `--image`, and record it
alongside the run's settings and seeds.

## Cluster installation

On a cluster with Apptainer:

```bash
bash install.sh --pull-sif
cp slurm-scripts/cluster.env.example slurm-scripts/cluster.env
```

Edit `cluster.env` for the account, partition, resource limits and paths.
The default SIF location is `/scratch/$USER/containers/electra.sif`; use
`--sif-dir`, `--sif-name` or `--sif` to select another location.
Continue with the [SLURM workflow](running/slurm.md).

## Python orchestration without a container

```bash
python3 -m venv /tmp/electra-runtime
/tmp/electra-runtime/bin/python -m pip install -e .
/tmp/electra-runtime/bin/electra --help
```

This installs the orchestration CLI only. The `ehijing` and `smash` executables
and their physics dependencies must separately be available on `PATH`.
Run commands from the repository root so relative settings paths resolve.
The [local workflow](running/local.md) shows container paths; outside the
container, use their corresponding host paths.
