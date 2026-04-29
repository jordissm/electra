"""
ELECTRA: eHIJING → SMASH orchestration CLI

Design principles:
- Filesystem is the database
- Manifest defines the contract between stages
- Same commands work locally and on SLURM
- One task = one (event_id, replica_id)
"""

from __future__ import annotations

import os
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def atomic_done_marker(path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("ok\n", encoding="utf-8")
    tmp.rename(path)


def hash_seed(*items: Any, bits: int = 63) -> int:
    h = hashlib.sha256()
    for it in items:
        h.update(str(it).encode())
    return int(h.hexdigest(), 16) & ((1 << bits) - 1)


def parse_event_id_from_path(event_file: Path) -> int:
    """
    Accepts names like:
      event_00000000.oscar
      event_00000000
    """
    name = event_file.stem if event_file.suffix else event_file.name
    if not name.startswith("event_"):
        raise ValueError(f"Could not parse event id from filename: {event_file}")
    return int(name[len("event_") :])


def event_shard_dir(base: Path, event_id: int, shard_size: int = 1000) -> Path:
    lo = (event_id // shard_size) * shard_size
    hi = lo + shard_size - 1
    return base / f"events_{lo:08d}-{hi:08d}"


def run(
    cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None
) -> None:
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd) if cwd is not None else None, env=env)


def load_profiles_jsonl(index_path: Path) -> List[Dict[str, Any]]:
    """
    Load profiles from a JSONL index.

    Each line is a JSON object with at least:
      - "id": a unique profile id (string)
      - "relpath": sharded relative path to the file (string), e.g. "ab/ab12cd.dat"

    Optional:
      - "sha256": content hash
      - "meta": arbitrary metadata
    """
    profiles: List[Dict[str, Any]] = []
    with index_path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "id" not in rec:
                raise ValueError(f"{index_path}:{lineno} missing required key 'id'")
            if "relpath" not in rec:
                raise ValueError(
                    f"{index_path}:{lineno} missing required key 'relpath'"
                )
            profiles.append(rec)
    return profiles


def deduce_profiles_root_from_index(index_path: Path) -> Path:
    """
    With the sharder behavior:
      out_root/profiles.jsonl
      out_root/<shards...>/<files...>
    so profiles_root is always the parent directory of the index file.
    """
    return index_path.parent.resolve()


def resolve_profile_path(profiles_root: Path, profile_rec: Dict[str, Any]) -> Path:
    """
    Turn a profile record into an absolute file path.
    profile_rec["relpath"] is assumed already sharded (e.g. "ab/xyz.dat").
    """
    return (profiles_root / str(profile_rec["relpath"])).resolve()


# -----------------------------------------------------------------------------
# Paths / layout
# -----------------------------------------------------------------------------


def run_layout(run_dir: Path) -> Dict[str, Path]:
    return {
        "run": run_dir,
        "manifest": run_dir / "manifest.jsonl",
        "ehijing_events": run_dir / "ehijing" / "events",
        "ehijing_logs": run_dir / "ehijing" / "logs",
        "smash": run_dir / "smash",
        "meta": run_dir / "metadata",
        "profiles_root": run_dir / "profiles",
        "profiles_index": (run_dir / "profiles" / "profiles.jsonl"),
    }


def ehijing_run_layout(run_dir: Path) -> Dict[str, Path]:
    return {
        "run": run_dir,
        "manifest": run_dir / "manifest.jsonl",
        "events": run_dir / "events",
        "logs": run_dir / "logs",
        "tables": run_dir / "tables",
        "diskinematics": run_dir / "DISKinematics.meta.jsonl",
    }


# -----------------------------------------------------------------------------
# Stage A: eHIJING
# -----------------------------------------------------------------------------


def ehijing_task(
    run_dir: Path,
    first_event_id: int,
    nevents: int,
    chunk_size: Optional[int],
    base_seed: int,
    *,
    Z: int,
    A: int,
    mode: int,
    K: float,
    table_path: Path,
    config_file: Path,
) -> None:
    layout = ehijing_run_layout(run_dir)
    mkdir(layout["events"])
    mkdir(layout["logs"])

    events_dir = layout["events"]

    if nevents <= 0:
        return

    # Optional chunk-level done marker
    chunk_done = events_dir / f".chunk_{first_event_id:08d}_{nevents}.done"
    if chunk_done.exists():
        return

    # Ensure tables + events dirs exist (fixes your earlier filesystem error)
    mkdir(Path(table_path))

    # Seed handling:
    # Your current ehijing main.cpp does NOT accept a seed argument,
    # so we can only *record* a deterministic seed for now.
    PYTHIA_SEED_MAX = 900_000_000  # Pythia8 allowed max
    seed = 1 + (hash_seed(base_seed, first_event_id, nevents) % PYTHIA_SEED_MAX)

    # Run one triggered event per call, and write into the events directory.
    # NOTE: table_path is a directory; config_file is the .setting file.
    cmd = [
        "ehijing",
        "--number-of-events",
        str(nevents),
        "--first-event-id",
        str(first_event_id),
        "--chunk-size",
        str(chunk_size) if chunk_size is not None else str(nevents),
        "--Z",
        str(Z),
        "--A",
        str(A),
        "--medium-modification-mode",
        str(mode),
        "--K",
        str(K),
        "--tabulation-path",
        str(Path(table_path)),
        "--run-path",
        str(events_dir),
        "--hard-process-config",
        str(Path(config_file)),
        "--seed",
        str(seed),
    ]

    run(cmd)

    atomic_done_marker(chunk_done)

    record = {
        "first_event_id": first_event_id,
        "number_of_events": nevents,
        "chunk_size": chunk_size,
        "ehijing_seed": seed,
        "Z": Z,
        "A": A,
        "medium_modification_mode": mode,
        "K": K,
        "tabulation_path": str(Path(table_path)),
        "hard_process_config": str(Path(config_file)),
        "events_dir": str(events_dir),
    }

    with layout["manifest"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# -----------------------------------------------------------------------------
# Stage B: SMASH
# -----------------------------------------------------------------------------


def smash_physical_event_task(
    *,
    run_dir: Path,
    event_file: Path,
    cfg_path: Path,
    profile_rec: Dict[str, Any],
    profiles_root: Path,
    nreplicas: int,
    base_seed: int,
) -> None:
    """
    Run SMASH for one physical eHIJING event file and one xsec profile.
    SMASH produces nreplicas stochastic replays internally.

    output:
      run/smash/<evt_tag>/profile_<profile_id>/
    """
    layout = run_layout(run_dir)

    event_id = parse_event_id_from_path(event_file)
    event_tag = f"event_{event_id:08d}"
    profile_id = str(profile_rec["id"])

    shard_dir = event_shard_dir(layout["smash"] / "events", event_id, shard_size=1000)
    out_dir = shard_dir / event_tag / f"profile_{profile_id}"
    done = out_dir / ".done"

    if done.exists():
        return

    mkdir(out_dir)

    cfg = cfg_path.resolve()
    if not cfg.exists():
        raise FileNotFoundError(f"Missing universal SMASH config: {cfg}")

    profile_path = resolve_profile_path(profiles_root, profile_rec)
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Missing profile file for {profile_id}: {profile_path}"
        )

    # Deterministic seed per (physical event, profile)
    smash_seed = hash_seed(base_seed, event_tag, profile_id)

    cmd = [
        "smash",
        "-i",
        str(cfg),
        "-m",
        "List",
        "-f",
        "-c",
        f"General: {{ Randomseed: {smash_seed}, Nevents: {nreplicas} }}",
        "-c",
        (
            "Modi: { List: { "
            f"File_Directory: '{event_file.parent}', "
            f"Filename: '{event_file.name}' "
            "} }"
        ),
        "-c",
        (
            "General: { Cross_Section_Scaling_Factor: { "
            "Type: File, "
            f"Path: '{profile_path}' "
            "} }"
        ),
        "-o",
        str(out_dir),
    ]

    run(cmd, cwd=out_dir)
    atomic_done_marker(done)


# -----------------------------------------------------------------------------
# Command handlers
# -----------------------------------------------------------------------------


def cmd_ehijing(args: argparse.Namespace) -> None:
    run_path = getattr(args, "run_path", None)
    table_arg = getattr(args, "tabulation_path", None)
    config_arg = getattr(args, "hard_process_config", None)
    nevents_arg = getattr(args, "number_of_events", None)
    mode_arg = getattr(args, "medium_modification_mode", None)

    if config_arg is None:
        raise ValueError("Missing eHIJING config file")
    if nevents_arg is None:
        raise ValueError("Missing eHIJING number of events")
    if mode_arg is None:
        raise ValueError("Missing eHIJING medium modification mode")
    if run_path is None:
        raise ValueError("Missing eHIJING run path")

    config_file = Path(config_arg).resolve()
    if not config_file.exists():
        raise FileNotFoundError(f"Missing eHIJING config file: {config_file}")

    run_dir = Path(run_path).resolve()
    mkdir(run_dir)

    base_seed = int(args.seed)

    table_path = (
        Path(table_arg).resolve() if table_arg is not None else run_dir / "tables" / "K"
    )

    ehijing_task(
        run_dir,
        int(args.first_event_id),
        int(nevents_arg),
        int(args.chunk_size) if hasattr(args, "chunk_size") else None,
        base_seed,
        Z=int(args.Z),
        A=int(args.A),
        mode=int(mode_arg),
        K=float(args.K),
        table_path=table_path,
        config_file=config_file,
    )


def cmd_smash(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    mkdir(run_dir)
    layout = run_layout(run_dir)

    events_dir = layout["ehijing_events"]
    if not events_dir.exists():
        raise FileNotFoundError(f"Missing eHIJING events directory: {events_dir}")

    event_files_all = sorted(events_dir.rglob("event_*.oscar"))
    if not event_files_all:
        raise FileNotFoundError(
            f"No sharded eHIJING OSCAR files found in: {events_dir}"
        )

    first_event_id = int(args.first_event_id)
    if first_event_id < 0:
        raise ValueError("--first-event-id must be >= 0")

    E_req = int(args.nevents)
    if E_req <= 0:
        raise ValueError("--nevents must be > 0")

    event_files = event_files_all[first_event_id : first_event_id + E_req]
    E = len(event_files)

    if E == 0:
        raise FileNotFoundError(
            f"Requested event slice [{first_event_id}, {first_event_id + E_req}) "
            f"but no events were found in {events_dir}"
        )

    profiles_index = Path(args.profiles_index).resolve()
    if not profiles_index.exists():
        raise FileNotFoundError(f"Missing profiles index: {profiles_index}")

    profiles_root = deduce_profiles_root_from_index(profiles_index)
    if not profiles_root.is_dir():
        raise NotADirectoryError(
            f"Deduced profiles root is not a directory: {profiles_root}"
        )

    profiles = load_profiles_jsonl(profiles_index)
    if not profiles:
        raise FileNotFoundError(f"No profiles found in: {profiles_index}")

    if args.nprofiles is not None:
        profiles = profiles[: int(args.nprofiles)]
    P = len(profiles)
    if P == 0:
        raise FileNotFoundError("No profiles available after applying --nprofiles")

    T = E * P

    # Decide mode
    mode = str(args.task_mode)
    task_id = args.task_id
    slurm_tid = os.environ.get("SLURM_ARRAY_TASK_ID")

    if mode == "auto":
        if task_id is None and slurm_tid is not None:
            task_id = int(slurm_tid)
            mode = "one"
        else:
            mode = "all"

    if mode == "one":
        if task_id is None:
            raise ValueError(
                "--task-id is required in task-mode=one (or set SLURM_ARRAY_TASK_ID with task-mode=auto)"
            )
        if task_id < 0 or task_id >= T:
            raise ValueError(
                f"task-id {task_id} out of range [0, {T-1}] for E={E}, P={P}"
            )

        ev_idx = task_id // P
        pr_idx = task_id % P

        ev = event_files[ev_idx]
        prof = profiles[pr_idx]

        smash_physical_event_task(
            run_dir=run_dir,
            event_file=ev,
            cfg_path=Path(args.config_file).resolve(),
            profile_rec=prof,
            profiles_root=profiles_root,
            nreplicas=int(args.nreplicas),
            base_seed=int(args.seed),
        )
        return

    # mode == "all"
    for ev in event_files:
        for prof in profiles:
            smash_physical_event_task(
                run_dir=run_dir,
                event_file=ev,
                cfg_path=Path(args.config_file).resolve(),
                profile_rec=prof,
                profiles_root=profiles_root,
                nreplicas=int(args.nreplicas),
                base_seed=int(args.seed),
            )


# -----------------------------------------------------------------------------
# CLI wiring
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="electra")
    sp = p.add_subparsers(dest="cmd", required=True)

    # eHIJING
    pe = sp.add_parser("ehijing")
    spe = pe.add_subparsers(dest="sub", required=True)
    per = spe.add_parser("run")
    per.add_argument("--Z", type=int, default=1)
    per.add_argument("--A", type=int, default=2)
    per.add_argument("--medium-modification-mode", type=int, default=0)
    per.add_argument("--K", type=float, default=4.0)
    per.add_argument("--run-path", required=True)
    per.add_argument("--number-of-events", type=int, required=True)
    per.add_argument("--seed", type=int, default=12345)
    per.add_argument(
        "--first-event-id",
        type=int,
        default=0,
        help="Global first event ID for this chunk (default: 0)",
    )
    per.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Optional chunk size for eHIJING runs (default: 1, i.e. no chunking)",
    )
    per.add_argument(
        "--tabulation-path",
        default=None,
        help="Directory with eHIJING tables, e.g. output/ehijing/runs/0/tables/K",
    )
    per.add_argument(
        "--hard-process-config",
        required=True,
        help="eHIJING config/setting file, e.g. input/ehijing/experiments/hermes.setting",
    )
    per.set_defaults(func=cmd_ehijing)

    # SMASH
    ps = sp.add_parser("smash")
    sps = ps.add_subparsers(dest="sub", required=True)
    psr = sps.add_parser("run")
    psr.add_argument("--run-dir", required=True)
    psr.add_argument("--config-file", required=True, help="Universal SMASH config.yaml")
    psr.add_argument("--nevents", type=int, required=True)
    psr.add_argument("--nreplicas", type=int, required=True)
    psr.add_argument("--seed", type=int, default=98765)
    psr.add_argument("--profiles-index", required=True, help="Path to profiles.jsonl")
    psr.add_argument(
        "--nprofiles",
        type=int,
        default=None,
        help="Optional: limit number of profiles to run per event",
    )
    psr.add_argument(
        "--task-mode",
        choices=["auto", "all", "one"],
        default="auto",
        help="auto: if SLURM_ARRAY_TASK_ID is set run one task; else run all. "
        "all: run all tasks locally. one: run exactly one task-id.",
    )
    psr.add_argument(
        "--task-id",
        type=int,
        default=None,
        help="Run exactly one task (event_idx, profile_idx) mapped from task-id.",
    )
    psr.add_argument(
        "--first-event-id",
        type=int,
        default=0,
        help="Global first event index to process from the sorted eHIJING event list",
    )
    psr.set_defaults(func=cmd_smash)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
