# Installation

Use the packaged container to run ELECTRA without building the physics
dependencies locally. Docker is used for local execution; SLURM scripts use
Apptainer and a SIF image. Python utilities require Python 3.10 or newer.

## Local installation

From the repository root, with Docker available:

```bash
bash install.sh
./electra-shell -- electra --help
```

The installer creates `electra-shell`, prepares input/output directories,
and copies packaged utilities. Existing utility files are preserved; default
input files are copied only when the input directory is empty. Use
`bash install.sh --help` for paths and image overrides.

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
