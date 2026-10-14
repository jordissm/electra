# Output layout and formats

## Run directories

For a parent run directory `<run>`, invoke eHIJING with `--run-path <run>/ehijing`
and SMASH with `--run-dir <run>`:

```text
<run>/
  ehijing/
    manifest.jsonl
    events/
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
```

Event names use a minimum width of eight digits. eHIJING uses `--chunk-size`
as the shard width; SMASH uses a fixed width of 1000 IDs. The example above
shows a width of 1000 in both stages. A shard directory describes an ID range,
not the number of events actually present. eHIJING's `.chunk_<first-id>_<count>.done` markers
are in its events directory.

## OSCAR and metadata

eHIJING writes an OSCAR2013-style particle list and per-event JSON metadata.
The current particle-column header is:

```text
t x y z mass p0 px py pz pdg ID charge prod_time form_time xsecfac
```

Momentum and mass are in GeV. Positions and coordinate times use fm and fm/c.
Particle positions are extrapolated to the output `t=0` surface; `prod_time`
and `form_time` retain their separate assignments. These are coordinate times,
not proper-time intervals. See [unit conventions](_generated/units.md).

Metadata includes the physical event's kinematics and nuclear bookkeeping.
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
