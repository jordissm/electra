# SLURM workflow

The submit scripts read `slurm-scripts/cluster.env`, then accept `KEY=value`
arguments for submission settings. Configure the account, partition, SIF path
and host output directory before submitting jobs.

## Submit generation

```bash
bash slurm-scripts/ehijing_submit.sh \
  EXPERIMENT=hermes NEVENTS=1000 CHUNK_SIZE=100 SEED=12345
```

`EXPERIMENT` is required and selects a directory under
`input/ehijing/experiments/`. `CONFIG_PATH`, `HADRONIZATION_CONFIG_PATH` and
`DIS_CUTS_CONFIG_PATH` can override its individual files. The supplied bundle
is `hermes`.

The script reserves a numeric run ID, prints the run directory and submits
an array. A postprocessing job runs after the array succeeds and combines
per-event metadata into `ehijing/DISKinematics.meta.jsonl`.
An explicit `RUN_ID` must be unused unless `OVERWRITE_RUN=true` is supplied.
Prefer a new run ID for a new configuration.

The script defaults to Generalized Higher Twist (`MED_MODIF_MODE=1`). Set
`MED_MODIF_MODE=0` in `cluster.env`, the environment, or the submission arguments
to select Higher Twist. Submission arguments take precedence over `cluster.env`.
The physical-parameter section still assigns `Z=1`, `A=2` and `K=4.0` directly,
overriding their environment values; inspect it before using a different target.
Optional shared-target controls are passed through using `NUCLEAR_TARGET`,
`NUCLEON_WIDTH_FM`, `NUCLEAR_RADIUS_FM` and `NUCLEAR_SURFACE_FM`.

`SEED` is forwarded unchanged to every array task. Its default is `12345` for
eHIJING and `98765` for SMASH. Keep eHIJING chunk starts fixed for replay; SLURM
job IDs and execution order do not enter derivation. See the [seed and resume
contract](local.md#reproducibility-and-resuming).

## Submit transport

Wait for generation to finish. Prepare the profile index and compatible SMASH
configuration as described in the [local workflow](local.md).
Set `RUN_DIR` to the parent of the generated `ehijing` directory:

```bash
bash slurm-scripts/smash_submit.sh \
  RUN_DIR=/absolute/path/to/output/runs/0 \
  CONFIG_FILE=/absolute/path/to/output/runs/0/smash-config.yaml \
  PROFILES=/absolute/path/to/output/runs/0/profiles/profiles.jsonl \
  NEVENTS=1000 CHUNK_SIZE=100 NREPLICAS=1 NPROFILES=1 SEED=98765
```

Replace the absolute paths and run ID with those for your run. Files must be
visible to the container's binds. `RUN_DIR` defaults to run `0`; it does not
automatically select the most recent eHIJING run. The script does not establish
a dependency on the generation job for you. SMASH chunk sizes can differ from
eHIJING chunk sizes; its selected events must already exist.

Array tasks map to event/profile pairs. The CLI's `auto` task mode uses
`SLURM_ARRAY_TASK_ID` when present; see the [CLI reference](../reference/cli.md).

## Analysis

The separate analysis submission script accepts a run ID:

```bash
bash slurm-scripts/analysis_submit.sh RUN_ID=0
```

Inspect its resource and binning options before submission. Rivet-specific
build instructions are in the [analysis guide](../analysis/rivet.md).
