# Output layout and formats

## Run directories

For a parent run directory `<run>`, invoke eHIJING with `--run-path <run>/ehijing`
and SMASH with `--run-dir <run>`:

```text
<run>/
  ehijing/
    manifest.jsonl
    events/
      .chunk_00000000_1000.done
      .chunk_00000000_1000.provenance.json
      events_00000000-00000999/
        event_00000000.oscar
        event_00000000.meta.json
        event_00000000.history          (when enabled)
        event_00000000.fragmentation    (when enabled)
    logs/
    tables/
    DISKinematics.meta.jsonl            (SLURM postprocessing)
  profiles/
    profiles.jsonl
    <hash-prefix>/<profile-id>.dat
  smash/
    events/
      events_00000000-00000999/
        event_00000000/
          profile_<profile-id>/
            .done
            seed_provenance.json
```

Event names use a minimum width of eight digits. eHIJING uses `--chunk-size`
as the shard width; SMASH uses a fixed width of 1000 IDs. The example above
shows a width of 1000 in both stages. A shard directory describes an ID range,
not the number of events actually present. eHIJING's `.chunk_<first-id>_<count>.done` markers
are in its events directory, alongside `.chunk_<first-id>_<count>.provenance.json`.
SMASH stores `seed_provenance.json` beside each `.done` marker. These records
identify the completed request and protect against skipping work with changed seeds.
The eHIJING manifest includes the policy, master seed, effective streams and input
fingerprints; `ehijing_seed` remains the value passed to the executable, which is
now the master seed rather than a pre-reduced PYTHIA seed.

## OSCAR and metadata

eHIJING writes an OSCAR2013-style particle list and per-event JSON metadata.
The current particle-column header is:

```text
t x y z mass p0 px py pz pdg ID charge prod_time form_time xsecfac prod_time_status
```

Momentum and mass are in GeV. Positions and coordinate times use fm and fm/c.
Particle positions are extrapolated to the output `t=0` surface; `prod_time`
and `form_time` retain their separate assignments. These are coordinate times,
not proper-time intervals. See [unit conventions](_generated/units.md).

Metadata includes the physical event's kinematics and nuclear bookkeeping.
Its `reproducibility` object records master seed, policy, chunk start, successful
attempt, effective stream seeds and input SHA-256 digests. See the [replay
contract](running/local.md#reproducibility-and-resuming).

| Reproducibility field | Meaning |
| --- | --- |
| `policy` | Versioned derivation, currently `electra-seeds-v1` |
| `master_seed` | Unsigned 64-bit master, stored as a decimal string |
| `first_event_id` | Chunk start used in derivation, independent of output shard width |
| `attempt` | Successful attempt number for this output event; includes rejected attempts across 15-attempt batches |
| `streams` | Effective PYTHIA seed integers and decimal-string 64-bit inputs to other engines' `seed_seq` |
| `inputs_sha256` | Settings and table content digests, independent of path spelling |

These are initial stream seeds, not RNG-state checkpoints for replaying an
individual event without its preceding chunk history. Histories attach the same
JSON object as the completed output observation's `reproducibility` attribute.
The [stream inventory](_generated/reproducibility.md) identifies active and
currently unused streams.

The [nuclear-target guide](_generated/nuclear-target.md) explains the identity
ledger and spectator policies. The SLURM postprocessing job aggregates metadata;
the local CLI does not automatically produce that aggregate.

## Histories and traces

| File | Content | Coordinates |
| --- | --- | --- |
| `.history` | Multiple diagnostic HepMC3 snapshots of one physical event | HepMC positions in mm; four-coordinate attributes `(x,y,z,ct)` |
| `.fragmentation` | Native string/vertex diagnostic records | `(t,x,y,z)`, time in fm/c and position in fm |

Histories are observation records, with serialization anchors and missing
spacetime information explicitly marked. Their snapshot sequence is execution
order. They are not a reconstructed physical worldline graph. Read the full
[history contract](_generated/history.md) before counting particles or drawing
trajectories.

## SMASH selection and profile index

SMASH finds `event_*.oscar` recursively beneath `<run>/ehijing/events`, sorts
them and takes a slice. Its `--first-event-id` is an index in that sorted list;
if event IDs contain gaps, the slice start need not equal a physical event ID.

Each profile-index line is JSON containing `id` and `relpath`. The profile
root is the index file's parent directory; optional `sha256` and `meta` fields
may also be present. Output for every event/profile pair stays separate.
