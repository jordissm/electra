# Python orchestration API

The orchestration module builds paths, selects tasks and invokes external
executables. It validates unsigned 64-bit CLI master seeds, forwards the eHIJING
master unchanged, and derives SMASH event/profile seeds. Importing it for this
reference does not run simulations.

`master_seed()` accepts ASCII decimal values in `[0, 18446744073709551615]`.
The CLI defaults are `12345` for eHIJING and `98765` for SMASH. `hash_seed()`
hashes the ASCII canonical JSON array `[SEED_POLICY, *items]` with SHA-256,
without separator whitespace, then retains the requested low bits (63 by
default). Field boundaries and JSON types are significant. SMASH calls it with
`("smash", master_seed, event_tag, profile_id)`; eHIJING performs its own
versioned chunk/stream derivation and PYTHIA boundary conversion.

The task functions validate completed request fingerprints before skipping
work and save provenance before creating completion markers. See the
[seed and replay contract](../_generated/reproducibility.md) for the guarantee,
recorded inputs and rebuild requirements.

```{eval-rst}
.. automodule:: electra.cli
   :members: build_parser, main, master_seed, hash_seed, event_shard_dir, run_layout, ehijing_run_layout, load_profiles_jsonl, resolve_profile_path, ehijing_task, smash_physical_event_task
   :undoc-members:
```
