# Local workflow

Commands below are examples for a new run named `demo`. They generate events
only when you execute them. Choose the physical settings and sample size for
your study; the example uses the supplied HERMES settings and CLI defaults.

## Generate eHIJING events

After [installation](../getting-started.md), run from the repository root:

```bash
./electra-shell -- electra ehijing run \
  --run-path /workspace/output/runs/demo/ehijing \
  --number-of-events 10 \
  --chunk-size 10 \
  --seed 12345 \
  --hard-process-config /workspace/input/ehijing/experiments/hermes/hard_process.setting \
  --hadronization-config /workspace/input/ehijing/experiments/hermes/hadronization.setting \
  --dis-cuts-config /workspace/input/ehijing/experiments/hermes/dis_cuts.setting
```

The shell binds the host input/output directories to `/workspace/input` and
`/workspace/output`. The run path above ends in `ehijing` so that SMASH can
find its events under the parent run directory. See [output layout](../outputs.md).

Current eHIJING builds default to the shared nuclear target and disable
HepMC history collection. Add `--history on` when you need
[diagnostic histories](../_generated/history.md). Optional target controls
are described in [configuration](../configuration.md).

## Prepare SMASH inputs

The CLI expects a JSONL profile index, rather than a flat profile directory.
Create a separate working copy of the supplied profiles:

```bash
python3 utils/shard_profiles.py \
  --in-dir input/smash/xsec_scaling_factor_profiles \
  --out-root output/runs/demo/profiles \
  --mode copy
```

This creates `output/runs/demo/profiles/profiles.jsonl`. Each record identifies
a profile and its path relative to that index's directory.

Copy the supplied SMASH configuration to
`output/runs/demo/smash-config.yaml` and review it for the installed SMASH
version. The current modified list reader requires:

```yaml
Modi:
  List:
    Optional_Quantities: ["ID", "charge", "prod_time", "form_time", "xsecfac"]
```

The checked-in `input/smash/config_files/config.yaml` still lists
`begin_form_time` and omits `form_time`; it needs this interface update in
your working copy before use with the current reader. See
[unit conventions](../_generated/units.md). Retain the other configuration
sections and select the transport settings appropriate for your study.

## Run transport

```bash
./electra-shell -- electra smash run \
  --run-dir /workspace/output/runs/demo \
  --config-file /workspace/output/runs/demo/smash-config.yaml \
  --profiles-index /workspace/output/runs/demo/profiles/profiles.jsonl \
  --nevents 10 \
  --nreplicas 1 \
  --task-mode all
```

SMASH runs once for each selected event/profile pair, with stochastic replicas
generated internally. `--nprofiles` optionally limits the selected profiles.

## Reproducibility and resuming

Record the image revision, settings files, profile index, target parameters,
base seeds and chunk boundaries. eHIJING seeds depend on the base seed,
first event ID and event count; changing chunk boundaries changes the generated
sample. SMASH seeds depend on the base seed, event tag and profile ID.

Completed chunks and event/profile pairs have `.done` markers and are skipped
on later invocations. Markers do not compare settings or detect an image change.
Use a new run directory when changing configurations, profiles or executable
versions. The wrapper appends an eHIJING chunk record to `manifest.jsonl`.
