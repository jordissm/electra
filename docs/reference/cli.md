# Command-line reference

The Python CLI provides `electra ehijing run` and `electra smash run`.
There is no `electra pipeline run` command in the current parser.
For examples and path conventions, see the [local workflow](../running/local.md).

## Argument semantics

- Both stages accept `--seed` as an unsigned decimal master seed in
  `[0, 18446744073709551615]`, including reproducible zero. Defaults are `12345`
  for eHIJING and `98765` for SMASH.
- Python passes the eHIJING master seed unchanged. The executable derives its
  streams from the master, chunk first event ID and fixed stream identifiers
  under `electra-seeds-v1`. Each PYTHIA seed is converted to
  `1 + stream_seed % 900000000`, in `[1, 900000000]`, after settings are read.
  Event count and output shard width do not enter seed derivation; changing
  chunk starts changes the sample.
- SMASH receives a nonnegative 63-bit seed derived from the master, physical
  event tag and profile ID. Task ordering does not affect that seed.
- An omitted eHIJING `--chunk-size` is forwarded as the event count for that
  invocation. The parser's help text currently describes a default of 1;
  the wrapper implementation uses the invocation's event count.
- SMASH `--first-event-id` selects an index in the sorted file list.
- SMASH `--task-mode auto` selects one task when a SLURM array task ID is
  present, and all selected event/profile pairs otherwise.
- SMASH `--task-id` indexes the Cartesian product of selected events and
  profiles: event index is `task_id // number_of_profiles`, and profile index
  is `task_id % number_of_profiles`.
- Optional eHIJING history and nuclear controls inherit executable defaults
  when omitted. Current build behavior is described in the physics pages.

Completed tasks validate saved request fingerprints before skipping work.
Rebuild the bundled modified PYTHIA library/XML settings and eHIJING to adopt
this policy; its samples differ from historical seed behavior. See the
[seed and replay contract](../_generated/reproducibility.md) and
[resume guidance](../running/local.md#reproducibility-and-resuming).

The following help is generated at documentation build time from the parser.

```{include} ../_generated/cli-help.txt
:start-after: "# CLI help"
```
