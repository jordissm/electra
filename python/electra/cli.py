"""
ELECTRA: ELectron-ion Event generation Coupled to TRAnsport

Orchestration CLI for eHIJING event generation and SMASH hadronic transport.

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
import shutil
from functools import lru_cache
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


SEED_POLICY = "electra-seeds-v1"


def master_seed(value: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise argparse.ArgumentTypeError("seed must be an unsigned 64-bit decimal integer")
    number = int(value)
    if number > (1 << 64) - 1:
        raise argparse.ArgumentTypeError("seed must be an unsigned 64-bit decimal integer")
    return number


def hash_seed(*items: Any, bits: int = 63) -> int:
    """Hash a canonical JSON tuple; field boundaries and types are significant."""
    data = json.dumps([SEED_POLICY, *items], ensure_ascii=True, separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(data.encode("ascii")).digest(), "big") & ((1 << bits) - 1)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def table_digests(table_path: Path, mode: int) -> Dict[str, str]:
    # GHT is created only when the high-scale medium is enabled in settings.
    # A missing previously recorded table still fails the resume comparison.
    names = ["Qs.dat"]
    if mode == 1 and (table_path / "GHT.dat").exists():
        names.append("GHT.dat")
    return {name: file_sha256(table_path / name) for name in names}


@lru_cache(maxsize=8)
def _executable_sha256(path: str, modified_ns: int, size: int) -> str:
    # Many SMASH tasks share one executable; invalidate on file changes.
    return file_sha256(Path(path))


def executable_digest(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"Executable not found on PATH: {name}")
    path = Path(executable).resolve()
    stat = path.stat()
    return _executable_sha256(str(path), stat.st_mtime_ns, stat.st_size)


def completed_request(done: Path, provenance: Path, request: Dict[str, Any],
                      tables: Optional[Dict[str, str]] = None) -> bool:
    if not done.exists():
        return False
    if not provenance.exists():
        raise ValueError(f"Completed output has no seed provenance: {done}; use a new run directory")
    stored = json.loads(provenance.read_text(encoding="utf-8"))
    if stored["request"] != request or (tables is not None and stored["tables_sha256"] != tables):
        raise ValueError(f"Completed output has different seeds, settings, executable or tables: {done}; use a new run directory")
    return True


def save_provenance(path: Path, value: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


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


def resolve_nucleus(name: str, database: Optional[Path] = None, **overrides: Optional[float]) -> Dict[str, Any]:
    """Ask the executable's YAML reader for parameters without generating events."""
    command = ["ehijing", "--nucleus", name, "--describe-nucleus"]
    if database is not None:
        command.extend(["--nucleus-database", str(database)])
    for key, value in overrides.items():
        if value is not None:
            command.extend(["--" + key.replace("_", "-"), str(value)])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "eHIJING could not resolve the nucleus")
    return json.loads(result.stdout)


def ehijing_task(
    run_dir: Path,
    first_event_id: int,
    nevents: int,
    chunk_size: Optional[int],
    base_seed: int,
    *,
    Z: Optional[int] = None,
    A: Optional[int] = None,
    nucleus: Optional[str] = None,
    nucleus_database: Optional[Path] = None,
    mode: int,
    K: float,
    table_path: Path,
    config_file: Path,
    hadronization_config_file: Path,
    dis_cuts_config_file: Path,
    history: Optional[str] = None,
    nuclear_target: Optional[str] = None,
    nucleon_width_fm: Optional[float] = None,
    nuclear_radius_fm: Optional[float] = None,
    nuclear_surface_fm: Optional[float] = None,
) -> None:
    if nucleus is not None and (Z is not None or A is not None):
        raise ValueError("Use --nucleus or legacy --Z/--A, not both")
    if nucleus is None and Z is None and A is None:
        nucleus = "d"
    nucleus_record: Dict[str, Any] = {}
    if nucleus is not None:
        parameters = resolve_nucleus(nucleus, nucleus_database,
            nucleon_width_fm=nucleon_width_fm, nuclear_radius_fm=nuclear_radius_fm,
            nuclear_surface_fm=nuclear_surface_fm)
        Z, A = parameters["Z"], parameters["A"]
        nucleus_database = Path(parameters["nucleus_database"])
        nucleus_record = {
            "nucleus": nucleus,
            "nucleus_database_sha256": file_sha256(nucleus_database),
            "nucleus_parameters": {key: value for key, value in parameters.items()
                                   if key != "nucleus_database"},
        }
    elif Z is None or A is None:
        raise ValueError("Legacy target selection requires both --Z and --A")
    elif nucleus_database is not None:
        raise ValueError("--nucleus-database requires --nucleus")
    layout = ehijing_run_layout(run_dir)
    mkdir(layout["events"])
    mkdir(layout["logs"])

    events_dir = layout["events"]

    if nevents <= 0:
        return

    # Optional chunk-level done marker
    chunk_done = events_dir / f".chunk_{first_event_id:08d}_{nevents}.done"
    chunk_provenance = chunk_done.with_suffix(".provenance.json")
    request = {
        **nucleus_record,
        "seed_policy": SEED_POLICY, "master_seed": str(base_seed),
        "first_event_id": first_event_id, "number_of_events": nevents,
        "chunk_size": chunk_size if chunk_size is not None else nevents,
        "Z": Z, "A": A, "mode": mode, "K": K,
        "settings_sha256": {"hard_process": file_sha256(config_file),
                            "hadronization": file_sha256(hadronization_config_file),
                            "dis_cuts": file_sha256(dis_cuts_config_file)},
        "executable_sha256": executable_digest("ehijing"),
        "history": history, "nuclear_target": nuclear_target,
        "nucleon_width_fm": nucleon_width_fm,
        "nuclear_radius_fm": nuclear_radius_fm, "nuclear_surface_fm": nuclear_surface_fm,
    }
    # Different event counts produce different marker names, but may overlap
    # already completed records. Validate those too before launching a writer.
    for existing in events_dir.glob(".chunk_*_*.done"):
        _, first, count = existing.stem.lstrip(".").split("_")
        if max(first_event_id, int(first)) >= min(first_event_id + nevents, int(first) + int(count)):
            continue
        same = completed_request(existing, existing.with_suffix(".provenance.json"), request,
                                 table_digests(Path(table_path), mode))
        if same:
            return

    # Ensure tables + events dirs exist (fixes your earlier filesystem error)
    mkdir(Path(table_path))

    # The executable owns chunk/stream derivation and engine-specific conversion.
    seed = base_seed

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
        "--hadronization-config",
        str(Path(hadronization_config_file)),
        "--dis-cuts-config",
        str(Path(dis_cuts_config_file)),
        "--seed",
        str(seed),
    ]
    if nucleus is not None:
        cmd.extend(["--nucleus", nucleus, "--nucleus-database", str(nucleus_database)])
    else:
        cmd.extend(["--Z", str(Z), "--A", str(A)])

    if history is not None:
        cmd.extend(["--history", history])
    for flag, value in (("--nuclear-target", nuclear_target), ("--nucleon-width-fm", nucleon_width_fm),
                        ("--nuclear-radius-fm", nuclear_radius_fm), ("--nuclear-surface-fm", nuclear_surface_fm)):
        if value is not None:
            cmd.extend([flag, str(value)])
    run(cmd)
    if nucleus is not None and file_sha256(nucleus_database) != nucleus_record["nucleus_database_sha256"]:
        raise ValueError("Nucleus database changed during generation; refusing to mark the chunk complete")

    metadata_files = list(events_dir.rglob(f"event_{first_event_id:08d}.meta.json"))
    if len(metadata_files) != 1:
        raise ValueError("Expected one first-event metadata record from seeded eHIJING")
    effective = json.loads(metadata_files[0].read_text(encoding="utf-8"))["reproducibility"]
    if (effective["policy"] != SEED_POLICY or effective["master_seed"] != str(base_seed)
            or effective["first_event_id"] != first_event_id):
        raise ValueError("eHIJING seed provenance does not match the requested chunk")
    if nucleus is not None:
        expected_parameters = {**nucleus_record["nucleus_parameters"],
                               "nucleus_database": str(nucleus_database)}
        if (effective.get("nucleus_parameters") != expected_parameters or
                effective.get("inputs_sha256", {}).get("nucleus_database") !=
                nucleus_record["nucleus_database_sha256"]):
            raise ValueError("eHIJING nucleus provenance does not match the requested database and parameters")
    tables = table_digests(Path(table_path), mode)
    provenance = {"request": request, "tables_sha256": tables}
    save_provenance(chunk_provenance, provenance)

    record = {
        **nucleus_record,
        **({"nucleus_database": str(nucleus_database)} if nucleus is not None else {}),
        "first_event_id": first_event_id,
        "number_of_events": nevents,
        "chunk_size": chunk_size,
        "ehijing_seed": seed,  # Seed passed to the executable (master, since v1).
        "master_seed": str(base_seed), "seed_policy": SEED_POLICY,
        "effective_seeds": effective["streams"],
        "settings_sha256": request["settings_sha256"],
        "executable_sha256": request["executable_sha256"], "tables_sha256": tables,
        "Z": Z,
        "A": A,
        "medium_modification_mode": mode,
        "K": K,
        "tabulation_path": str(Path(table_path)),
        "hard_process_config": str(Path(config_file)),
        "hadronization_config": str(Path(hadronization_config_file)),
        "dis_cuts_config": str(Path(dis_cuts_config_file)),
        "events_dir": str(events_dir),
        "history": history if history is not None else "executable_default",
        "nuclear_target": nuclear_target if nuclear_target is not None else "executable_default",
        "nucleon_width_fm": nucleon_width_fm,
        "nuclear_radius_fm": nuclear_radius_fm,
        "nuclear_surface_fm": nuclear_surface_fm,
    }

    with layout["manifest"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    atomic_done_marker(chunk_done)


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
    smash_seed = hash_seed("smash", base_seed, event_tag, profile_id)
    request = {
        "seed_policy": SEED_POLICY, "master_seed": str(base_seed),
        "smash_seed": smash_seed, "event_id": event_id, "profile_id": profile_id,
        "nreplicas": nreplicas, "event_sha256": file_sha256(event_file),
        "config_sha256": file_sha256(cfg), "profile_sha256": file_sha256(profile_path),
        "executable_sha256": executable_digest("smash"),
    }
    provenance = out_dir / "seed_provenance.json"
    if completed_request(done, provenance, request):
        return

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
            "Collision_Term: { Cross_Section_Formation_Scaling: { "
            "Profile: { "
            f"Path: '{profile_path}' "
            "} } }"
        ),
        "-o",
        str(out_dir),
    ]

    run(cmd, cwd=out_dir)
    save_provenance(provenance, {"request": request})
    atomic_done_marker(done)


# -----------------------------------------------------------------------------
# Command handlers
# -----------------------------------------------------------------------------


def cmd_ehijing(args: argparse.Namespace) -> None:
    run_path = getattr(args, "run_path", None)
    table_arg = getattr(args, "tabulation_path", None)
    config_arg = getattr(args, "hard_process_config", None)
    hadronization_config_arg = getattr(args, "hadronization_config", None)
    dis_cuts_config_arg = getattr(args, "dis_cuts_config", None)
    nevents_arg = getattr(args, "number_of_events", None)
    mode_arg = getattr(args, "medium_modification_mode", None)

    if config_arg is None:
        raise ValueError("Missing eHIJING hard-process config file")
    if hadronization_config_arg is None:
        raise ValueError("Missing eHIJING hadronization config file")
    if dis_cuts_config_arg is None:
        raise ValueError("Missing eHIJING DIS cuts config file")
    if nevents_arg is None:
        raise ValueError("Missing eHIJING number of events")
    if mode_arg is None:
        raise ValueError("Missing eHIJING medium modification mode")
    if run_path is None:
        raise ValueError("Missing eHIJING run path")

    config_file = Path(config_arg).resolve()
    if not config_file.exists():
        raise FileNotFoundError(
            f"Missing eHIJING hard-process config file: {config_file}"
        )

    hadronization_config_file = Path(hadronization_config_arg).resolve()
    if not hadronization_config_file.exists():
        raise FileNotFoundError(
            f"Missing eHIJING hadronization config file: {hadronization_config_file}"
        )

    dis_cuts_config_file = Path(dis_cuts_config_arg).resolve()
    if not dis_cuts_config_file.exists():
        raise FileNotFoundError(
            f"Missing eHIJING DIS cuts config file: {dis_cuts_config_file}"
        )

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
        int(args.chunk_size) if args.chunk_size is not None else None,
        base_seed,
        Z=args.Z,
        A=args.A,
        nucleus=args.nucleus,
        nucleus_database=Path(args.nucleus_database).resolve() if args.nucleus_database else None,
        mode=int(mode_arg),
        K=float(args.K),
        table_path=table_path,
        config_file=config_file,
        hadronization_config_file=hadronization_config_file,
        dis_cuts_config_file=dis_cuts_config_file,
        history=getattr(args, "history", None),
        nuclear_target=getattr(args, "nuclear_target", None),
        nucleon_width_fm=getattr(args, "nucleon_width_fm", None),
        nuclear_radius_fm=getattr(args, "nuclear_radius_fm", None),
        nuclear_surface_fm=getattr(args, "nuclear_surface_fm", None),
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
    p = argparse.ArgumentParser(
        prog="electra",
        description="ELECTRA: ELectron-ion Event generation Coupled to TRAnsport",
    )
    sp = p.add_subparsers(dest="cmd", required=True)

    # eHIJING
    pe = sp.add_parser("ehijing")
    spe = pe.add_subparsers(dest="sub", required=True)
    per = spe.add_parser("run")
    per.add_argument("--nucleus", default=None,
                     help="Nucleus key in woods_saxon.yaml, e.g. d or C12 (default: d)")
    per.add_argument("--nucleus-database", default=None,
                     help="Override the nuclear parameter YAML; otherwise use eHIJING's database search")
    per.add_argument("--Z", type=int, default=None, help="Legacy atomic number; requires --A")
    per.add_argument("--A", type=int, default=None, help="Legacy mass number; requires --Z")
    per.add_argument("--medium-modification-mode", type=int, default=1,
                     help="Medium modification: 1 = Generalized Higher Twist (default), 0 = Higher Twist")
    per.add_argument("--K", type=float, default=4.0)
    per.add_argument("--run-path", required=True)
    per.add_argument("--number-of-events", type=int, required=True)
    per.add_argument("--seed", type=master_seed, default=12345,
                     help="Unsigned 64-bit master seed; derived per stream by electra-seeds-v1")
    per.add_argument(
        "--history", choices=("on", "off"), default=None,
        help="HepMC3 ASCII spacetime history (new eHIJING builds default to off)",
    )
    per.add_argument("--nuclear-target", choices=("on", "off"), default=None,
                     help="Shared Gaussian nuclear target (new builds default to on)")
    per.add_argument("--nucleon-width-fm", type=float, default=None)
    per.add_argument("--nuclear-radius-fm", type=float, default=None)
    per.add_argument("--nuclear-surface-fm", type=float, default=None)
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
        help="eHIJING hard-process setting file, e.g. input/ehijing/experiments/hermes_2007/hard_process.setting",
    )
    per.add_argument(
        "--hadronization-config",
        required=True,
        help="eHIJING hadronization setting file, e.g. input/ehijing/experiments/hermes_2007/hadronization.setting",
    )
    per.add_argument(
        "--dis-cuts-config",
        required=True,
        help="eHIJING DIS cuts file, e.g. input/ehijing/experiments/hermes_2007/dis_cuts.setting",
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
    psr.add_argument("--seed", type=master_seed, default=98765,
                     help="Unsigned 64-bit master seed; SMASH receives a derived nonnegative 63-bit seed")
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
