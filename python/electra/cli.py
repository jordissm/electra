"""
ELECTRA: eHIJING → SMASH orchestration CLI

Design principles:
- Filesystem is the database
- Manifest defines the contract between stages
- Same commands work locally and on SLURM
- One task = one (event_id, replica_id)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


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


def stage_tabulations(
    out_dir: Path, cache_tabulations: Optional[Path], mode: str = "auto"
) -> None:
    """
    Ensure out_dir/tabulations exists, populated from cache_tabulations.

    mode:
      - "symlink": always symlink
      - "copy": always copy
      - "auto": try symlink, fall back to copy
    """
    if cache_tabulations is None:
        return

    print(f"Staging tabulations into {out_dir} from cache: {cache_tabulations}")

    cache_tabulations = Path(cache_tabulations).resolve()
    if not cache_tabulations.exists():
        raise FileNotFoundError(
            f"Tabulations cache does not exist: {cache_tabulations}"
        )
    if not cache_tabulations.is_dir():
        raise NotADirectoryError(
            f"Tabulations cache is not a directory: {cache_tabulations}"
        )

    dst = (out_dir / "tabulations").resolve()

    # If already present, do nothing (keeps idempotency)
    if dst.exists() or dst.is_symlink():
        return

    if mode not in {"auto", "symlink", "copy"}:
        raise ValueError(f"Invalid tabulations mode: {mode}")

    def _do_symlink() -> None:
        dst.symlink_to(cache_tabulations, target_is_directory=True)

    def _do_copy() -> None:
        shutil.copytree(cache_tabulations, dst, dirs_exist_ok=False)

    if mode == "symlink":
        _do_symlink()
        return
    if mode == "copy":
        _do_copy()
        return

    # auto
    try:
        _do_symlink()
    except OSError:
        _do_copy()


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


# -----------------------------------------------------------------------------
# Stage A: eHIJING
# -----------------------------------------------------------------------------


def ehijing_task(
    run_dir: Path,
    event_id: int,
    base_seed: int,
    *,
    Z: int,
    A: int,
    mode: int,
    K: float,
    table_path: Path,
    config_file: Path,
) -> None:
    layout = run_layout(run_dir)
    mkdir(layout["ehijing_events"])
    mkdir(layout["ehijing_logs"])

    # Your ehijing writes evt_000000.oscar etc into an output directory.
    # We mark completion per event_id once that file exists.
    out_evt = layout["ehijing_events"] / f"evt_{event_id:06d}.oscar"
    done = out_evt.with_suffix(".done")
    if done.exists():
        return

    # Ensure tables + events dirs exist (fixes your earlier filesystem error)
    mkdir(Path(table_path))
    mkdir(layout["ehijing_events"])

    # Seed handling:
    # Your current ehijing main.cpp does NOT accept a seed argument,
    # so we can only *record* a deterministic seed for now.
    seed = hash_seed(base_seed, event_id)

    # Run one triggered event per call, and write into the events directory.
    # NOTE: table_path is a directory; config_file is the .setting file.
    cmd = [
        "ehijing",
        "--nevents",
        "1",
        "--Z",
        str(Z),
        "--A",
        str(A),
        "--mode",
        str(mode),
        "--K",
        str(K),
        "--table-dir",
        str(Path(table_path)),
        "--run-dir",
        str(layout["ehijing_events"]),
        "--config-file",
        str(Path(config_file)),
        # "--seed", str(seed),  # enable if your ehijing supports it
    ]

    run(cmd)

    # Sanity check: did it actually create the file we expect?
    if not out_evt.exists():
        raise RuntimeError(
            f"ehijing finished but did not create expected output: {out_evt}\n"
            f"Command was: {' '.join(cmd)}"
        )

    atomic_done_marker(done)

    record = {
        "event_id": event_id,
        "ehijing_seed": seed,  # recorded (not yet used by ehijing)
        "Z": Z,
        "A": A,
        "mode": mode,
        "K": K,
        "table_path": str(Path(table_path)),
        "config_file": str(Path(config_file)),
        "path": str(out_evt),
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
    profile_rec: Dict[str, Any],
    profiles_root: Path,
    nreplicas: int,
    base_seed: int,
    tabulations_cache: Optional[Path] = None,
    tabulations_mode: str = "auto",
) -> None:
    """
    Run SMASH for one physical eHIJING event file and one xsec profile.
    SMASH produces nreplicas stochastic replays internally.

    output:
      run/smash/<evt_tag>/profile_<profile_id>/
    """
    layout = run_layout(run_dir)

    event_tag = event_file.stem  # "evt_000123"
    profile_id = str(profile_rec["id"])

    out_dir = layout["smash"] / event_tag / f"profile_{profile_id}"
    done = out_dir / ".done"
    if done.exists():
        return

    mkdir(out_dir)

    # Stage cached tabulations into this SMASH output directory
    stage_tabulations(
        layout["smash"] / event_tag, tabulations_cache, mode=tabulations_mode
    )

    cfg = (run_dir / "config.yaml").resolve()
    if not cfg.exists():
        raise FileNotFoundError(f"Missing universal SMASH config: {cfg}")

    profile_path = resolve_profile_path(profiles_root, profile_rec)
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Missing profile file for {profile_id}: {profile_path}"
        )

    # Deterministic seed per (physical event, profile)
    smash_seed = hash_seed(base_seed, event_tag)

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
# Local execution helpers
# -----------------------------------------------------------------------------


TaskFn = Callable[[], None]


def run_local(tasks: List[TaskFn], jobs: int) -> None:
    if jobs == 1:
        for t in tasks:
            t()
        return

    with ProcessPoolExecutor(max_workers=jobs) as exe:
        futures = [exe.submit(t) for t in tasks]
        for f in as_completed(futures):
            f.result()


# -----------------------------------------------------------------------------
# Command handlers
# -----------------------------------------------------------------------------


def cmd_ehijing(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    mkdir(run_dir)

    base_seed = int(args.seed)

    table_path = Path(args.table_path).resolve()
    config_file = Path(args.config_file).resolve()
    if not config_file.exists():
        raise FileNotFoundError(f"Missing ehijing config file: {config_file}")

    tasks: List[TaskFn] = [
        (
            lambda eid=eid: ehijing_task(
                run_dir,
                eid,
                base_seed,
                Z=int(args.Z),
                A=int(args.A),
                mode=int(args.mode),
                K=float(args.K),
                table_path=table_path,
                config_file=config_file,
            )
        )
        for eid in range(int(args.nevents))
    ]
    run_local(tasks, int(args.jobs))


def cmd_smash(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir).resolve()
    mkdir(run_dir)

    layout = run_layout(run_dir)

    events_dir = layout["ehijing_events"]
    if not events_dir.exists():
        raise FileNotFoundError(f"Missing eHIJING events directory: {events_dir}")

    event_files = sorted(events_dir.glob("evt_*.oscar"))
    if not event_files:
        raise FileNotFoundError(f"No per-event OSCAR files found in: {events_dir}")

    event_files = event_files[: int(args.nevents)]

    profiles_index = Path(args.profiles_index).resolve()
    if not profiles_index.exists():
        raise FileNotFoundError(f"Missing profiles index: {profiles_index}")

    profiles_root = deduce_profiles_root_from_index(profiles_index)
    if not profiles_root.exists():
        raise FileNotFoundError(
            f"Deduced profiles root does not exist: {profiles_root}"
        )
    if not profiles_root.is_dir():
        raise NotADirectoryError(
            f"Deduced profiles root is not a directory: {profiles_root}"
        )

    profiles = load_profiles_jsonl(profiles_index)
    if not profiles:
        raise FileNotFoundError(f"No profiles found in: {profiles_index}")

    if args.nprofiles is not None:
        profiles = profiles[: int(args.nprofiles)]

    tab_cache = (
        Path(args.tabulations_cache).resolve() if args.tabulations_cache else None
    )

    tasks: List[TaskFn] = []
    for ev in event_files:
        for prof in profiles:
            tasks.append(
                lambda ev=ev, prof=prof: smash_physical_event_task(
                    run_dir=run_dir,
                    event_file=ev,
                    profile_rec=prof,
                    profiles_root=profiles_root,
                    nreplicas=int(args.nreplicas),
                    base_seed=int(args.seed),
                    tabulations_cache=tab_cache,
                    tabulations_mode=str(args.tabulations_mode),
                )
            )

    run_local(tasks, int(args.jobs))


def cmd_pipeline(args: argparse.Namespace) -> None:
    cmd_ehijing(args)
    cmd_smash(args)


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
    per.add_argument("--mode", type=int, default=0)
    per.add_argument("--K", type=float, default=4.0)
    per.add_argument("--run-dir", required=True)
    per.add_argument("--nevents", type=int, required=True)
    per.add_argument("--seed", type=int, default=12345)
    per.add_argument("--jobs", type=int, default=1)
    per.add_argument(
        "--table-path",
        required=True,
        help="Directory with eHIJING tables, e.g. output/runs/ehijing/tables/K4p0",
    )
    per.add_argument(
        "--config-file",
        required=True,
        help="eHIJING config/setting file, e.g. input/ehijing/experiments/hermes.setting",
    )
    per.set_defaults(func=cmd_ehijing)

    # SMASH
    ps = sp.add_parser("smash")
    sps = ps.add_subparsers(dest="sub", required=True)
    psr = sps.add_parser("run")
    psr.add_argument("--run-dir", required=True)
    psr.add_argument("--nevents", type=int, required=True)
    psr.add_argument("--nreplicas", type=int, required=True)
    psr.add_argument("--seed", type=int, default=98765)
    psr.add_argument("--jobs", type=int, default=1)
    psr.add_argument("--profiles-index", required=True, help="Path to profiles.jsonl")
    psr.add_argument(
        "--nprofiles",
        type=int,
        default=None,
        help="Optional: limit number of profiles to run per event",
    )
    psr.add_argument(
        "--tabulations-cache",
        default=None,
        help="Path to cached SMASH 'tabulations' directory to stage into each output dir",
    )
    psr.add_argument(
        "--tabulations-mode",
        choices=["auto", "symlink", "copy"],
        default="auto",
        help="How to stage tabulations: auto tries symlink then copies; symlink forces link; copy forces copy",
    )
    psr.set_defaults(func=cmd_smash)

    # pipeline
    pp = sp.add_parser("pipeline")
    spp = pp.add_subparsers(dest="sub", required=True)
    ppr = spp.add_parser("run")
    ppr.add_argument("--Z", type=int, default=1)
    ppr.add_argument("--A", type=int, default=2)
    ppr.add_argument("--mode", type=int, default=0)
    ppr.add_argument("--K", type=float, default=4.0)
    ppr.add_argument("--table-path", required=True)
    ppr.add_argument("--config-file", required=True)
    ppr.add_argument("--run-dir", required=True)
    ppr.add_argument("--nevents", type=int, required=True)
    ppr.add_argument("--nreplicas", type=int, required=True)
    ppr.add_argument("--seed", type=int, default=12345)
    ppr.add_argument("--jobs", type=int, default=1)
    ppr.add_argument("--profiles-index", required=True, help="Path to profiles.jsonl")
    ppr.add_argument(
        "--nprofiles",
        type=int,
        default=None,
        help="Optional: limit number of profiles to run per event",
    )
    ppr.add_argument(
        "--tabulations-cache",
        default=None,
        help="Path to cached SMASH 'tabulations' directory to stage into each output dir",
    )
    ppr.add_argument(
        "--tabulations-mode",
        choices=["auto", "symlink", "copy"],
        default="auto",
        help="How to stage tabulations: auto tries symlink then copies; symlink forces link; copy forces copy",
    )
    ppr.set_defaults(func=cmd_pipeline)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
