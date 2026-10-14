# Command-line reference

The Python CLI provides `electra ehijing run` and `electra smash run`.
There is no `electra pipeline run` command in the current parser.
For examples and path conventions, see the [local workflow](../running/local.md).

## Argument semantics

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

The following help is generated at documentation build time from the parser.

```{include} ../_generated/cli-help.txt
:start-after: "# CLI help"
```
