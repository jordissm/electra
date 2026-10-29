# Local workflow

Commands below are examples for a new run named `demo`. They generate events
only when you execute them. Choose the physical settings and sample size for
your study; the example uses the supplied HERMES 2007 settings and CLI defaults.

## Generate eHIJING events

After [installation](../getting-started.md), run from the repository root:

```bash
./electra-shell -- electra ehijing run \
  --run-path /workspace/output/runs/demo/ehijing \
  --number-of-events 10 \
  --chunk-size 10 \
  --seed 12345 \
  --hard-process-config /workspace/input/ehijing/experiments/hermes_2007/hard_process.setting \
  --hadronization-config /workspace/input/ehijing/experiments/hermes_2007/hadronization.setting \
  --dis-cuts-config /workspace/input/ehijing/experiments/hermes_2007/dis_cuts.setting
```

The shell binds the host input/output directories to `/workspace/input` and
`/workspace/output`. The run path above ends in `ehijing` so that SMASH can
find its events under the parent run directory. See [output layout](../outputs.md).

For CLAS, another HERMES year, or an EMC beam energy, replace `hermes_2007`
in all three paths with a [supplied bundle name](../configuration.md#experiment-settings).

The ELECTRA CLI defaults to Generalized Higher Twist (GHT), mode `1`.
Add `--medium-modification-mode 0` to select Higher Twist (HT).

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
    Optional_Quantities: ["ID", "charge", "prod_time", "form_time", "xsecfac", "prod_time_status"]
```

The checked-in `input/smash/config_files/config.yaml` includes these fields.
Retain them in the working copy for current eHIJING output; historical lists
without `prod_time_status` need a matching configuration without that field.
See [unit conventions](../_generated/units.md). Retain the other configuration
sections and select the transport settings appropriate for your study.

The bundled config uses the imported Lund-based formation times by default
without a formation-time section. See [SMASH formation times](../configuration.md#smash-formation-times)
to select the secondary constant proper-time mode in your working copy.

## Run transport

```bash
./electra-shell -- electra smash run \
  --run-dir /workspace/output/runs/demo \
  --config-file /workspace/output/runs/demo/smash-config.yaml \
  --profiles-index /workspace/output/runs/demo/profiles/profiles.jsonl \
  --nevents 10 \
  --nreplicas 1 \
  --seed 98765 \
  --task-mode all
```

SMASH runs once for each selected event/profile pair, with stochastic replicas
generated internally. `--nprofiles` optionally limits the selected profiles.

## Reproducibility and resuming

`--seed` is an unsigned 64-bit ELECTRA master seed in
`[0, 18446744073709551615]`. Python defaults to `12345` for eHIJING and `98765`
for SMASH. The
`electra-seeds-v1` policy derives all eHIJING streams from the master and chunk
starting ID. PYTHIA receives seeds in `[1, 900000000]`; other engines receive
explicit seeds. Rejected attempts advance their streams without restarting them.
Replaying a chunk in fresh processes requires identical settings, tables,
executable/container and runtime environment. Changing event count or output
shard width preserves its prefix when using a fresh output directory with the
same chunk start. Changing chunk boundaries changes the sample.

Record the image revision, settings files, profile index, target parameters and
master seeds. The manifest records the seed policy and effective stream seeds;
per-event metadata also records successful-attempt numbers and input digests.
`master_seed` and the wide effective stream seeds are recorded as decimal
strings. The manifest's compatibility field `ehijing_seed` remains numeric and
records the master passed to the executable. These new semantics change the
sample for seeds used with older binaries; retain those binaries for historical
replay. Cross-architecture bitwise equality and matched parameter-variation
histories are outside the guarantee. The complete [stream inventory and
derivation](../_generated/reproducibility.md) are maintained with eHIJING.

New Qs/GHT tables use round-trip double precision and atomic publication, with
generation locked per table. Retain existing table bytes for replay; regenerating
historical tables can change numerical inputs. The fragmentation configuration
label uses the canonical hadronization-settings path: aliases of the same file
agree, while moving the file changes that diagnostic label.

SMASH receives a nonnegative 63-bit seed from SHA-256 of the ASCII canonical JSON
array `["electra-seeds-v1", "smash", master_seed, event_tag, profile_id]` with no
separator whitespace, then retaining the low 63 digest bits. The master is a JSON
integer and the event tag/profile ID are strings. Field boundaries and JSON types
are significant. Replicas
follow SMASH's existing deterministic seed progression, with each replica seed
reported in its log. Changing event/profile task ordering does not affect these
initial seeds; profile IDs remain part of the seed identity.

Completed chunks and event/profile pairs have `.done` markers and are skipped
only if saved seed/settings/executable fingerprints match. eHIJING also checks
table digests, and SMASH checks event/profile bytes and replica count. Overlapping
completed chunks with different requests, or historical markers without seed
provenance, are rejected. Use a new run directory for changed requests. The
wrapper writes provenance before marking completion and appends an eHIJING chunk
record to `manifest.jsonl`. Fingerprints do not identify every shared library or
runtime setting; retain the container/build revision and environment too.

Both the bundled modified PYTHIA library/XML settings and eHIJING must be rebuilt.
Python forwarding and resume checks can be checked without simulations:

```bash
PYTHONPATH=python python3 -m unittest discover -s tests -v
```

Full replay checks are opt-in and use only temporary outputs. The eHIJING check
uses small HT/GHT runs; the SMASH check uses two synthetic pions and two replicas,
including fresh-process and task-order replay. SMASH's initial integral cache
can take several minutes to compute in a debug build.

```bash
PYTHONPATH=python python3 tests/reproducibility_smoke.py --executable /path/to/ehijing
python3 tests/smash_seed_smoke.py --executable /path/to/smash
```
