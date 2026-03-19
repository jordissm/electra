#!/usr/bin/env python3
"""
Shard a flat directory of cross-section scaling profiles into a sharded tree
and generate profiles.jsonl for ELECTRA.

Default sharding:
  shard = first 2 hex chars of SHA256(content)
  relpath = "<shard>/<id><ext>"

Each output JSONL line has:
  {
    "id": "<profile-id>",
    "relpath": "<shard>/<filename>",
    "sha256": "<hex>",
    "bytes": <int>,
    "src_name": "<original filename>"
  }

Example:
  shard_profiles.py \
    --in-dir profiles_flat \
    --out-root profiles_sharded \
    --out-index profiles.jsonl \
    --mode hardlink
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def link_or_copy(src: Path, dst: Path, mode: str) -> None:
    """
    mode:
      - copy:    copy file bytes
      - move:    move file (renames if possible)
      - hardlink:create hardlink (fast, no extra bytes; same filesystem required)
      - symlink: symlink to original file (original must remain available)
    """
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "move":
        # Path.replace is an atomic rename when possible
        src.replace(dst)
    elif mode == "hardlink":
        os.link(src, dst)
    elif mode == "symlink":
        # Make symlink target absolute to avoid surprises
        dst.symlink_to(src.resolve())
    else:
        raise ValueError(f"Unknown mode: {mode}")


def pick_profile_id(src: Path, id_mode: str, sha256_hex: str) -> str:
    """
    id_mode:
      - stem:   use src.stem
      - name:   use src.name
      - sha256: use full sha256 hex
    """
    if id_mode == "stem":
        return src.stem
    if id_mode == "name":
        return src.name
    if id_mode == "sha256":
        return sha256_hex
    raise ValueError(f"Unknown id_mode: {id_mode}")


def normalize_ext(src: Path, keep_ext: bool, forced_ext: Optional[str]) -> str:
    if forced_ext is not None:
        if not forced_ext.startswith("."):
            forced_ext = "." + forced_ext
        return forced_ext
    if keep_ext:
        return src.suffix  # includes dot or empty
    return ""


def iter_files_flat(in_dir: Path, pattern: str) -> Iterable[Path]:
    # Non-recursive: flat directory only
    for p in sorted(in_dir.glob(pattern)):
        if p.is_file():
            yield p


def resolve_collision(dst: Path, collision: str, sha_src: str) -> Path:
    """
    If dst exists:
      - error: raise
      - skip:  return dst (caller will skip)
      - dedup: if existing file has same sha, reuse; otherwise error
      - rename: append suffix until unique
    """
    if not dst.exists():
        return dst

    if collision == "skip":
        return dst

    if collision == "error":
        raise FileExistsError(f"Destination already exists: {dst}")

    if collision == "dedup":
        # Dedup by content hash: if same sha, reuse; else error
        sha_existing = compute_sha256(dst)
        if sha_existing == sha_src:
            return dst
        raise FileExistsError(
            f"Destination exists with different content:\n  {dst}\n"
            f"  sha(existing)={sha_existing}\n  sha(new)={sha_src}"
        )

    if collision == "rename":
        base = dst.with_suffix("")  # drop suffix
        suffix = dst.suffix
        i = 1
        while True:
            cand = Path(f"{base}_{i}{suffix}")
            if not cand.exists():
                return cand
            i += 1

    raise ValueError(f"Unknown collision policy: {collision}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="shard_profiles.py")
    ap.add_argument("--in-dir", required=True, type=Path, help="Flat input directory with profile files")
    ap.add_argument("--out-root", required=True, type=Path, help="Output root directory for sharded files")
    ap.add_argument("--pattern", default="*.dat", help="Glob pattern in --in-dir (default: *.dat)")
    ap.add_argument(
        "--mode",
        choices=["copy", "move", "hardlink", "symlink"],
        default="hardlink",
        help="How to place files into the shard tree (default: hardlink)",
    )
    ap.add_argument(
        "--id-mode",
        choices=["stem", "name", "sha256"],
        default="stem",
        help="How to choose profile id (default: stem)",
    )
    ap.add_argument(
        "--shard-by",
        choices=["sha256"],
        default="sha256",
        help="Sharding scheme (currently only sha256)",
    )
    ap.add_argument(
        "--shard-len",
        type=int,
        default=2,
        help="Number of hex chars for shard directory from sha256 (default: 2)",
    )
    ap.add_argument(
        "--keep-ext",
        action="store_true",
        help="Keep original extension (default: False unless --ext is unset and file has suffix)",
    )
    ap.add_argument(
        "--ext",
        default=None,
        help="Force extension for output files (e.g. '.dat' or 'dat'). Overrides --keep-ext.",
    )
    ap.add_argument(
        "--collision",
        choices=["error", "skip", "dedup", "rename"],
        default="dedup",
        help="If destination exists: error/skip/dedup/rename (default: dedup)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute metadata and print planned actions, but do not write files/index",
    )

    args = ap.parse_args()

    in_dir: Path = args.in_dir.resolve()
    out_root: Path = args.out_root.resolve()
    out_index: Path = out_root / "profiles.jsonl"

    if in_dir == out_root:
        print(
            "ERROR: --in-dir and --out-root must be different directories.\n"
            "       Refusing to shard in-place to avoid data corruption.",
            file=sys.stderr,
        )
        return 2


    if not in_dir.exists() or not in_dir.is_dir():
        print(f"ERROR: --in-dir is not a directory: {in_dir}", file=sys.stderr)
        return 2

    if args.shard_len < 1 or args.shard_len > 64:
        print("ERROR: --shard-len must be between 1 and 64", file=sys.stderr)
        return 2

    # Prepare output dirs
    if not args.dry_run:
        safe_mkdir(out_root)

    files = list(iter_files_flat(in_dir, args.pattern))
    if not files:
        print(f"ERROR: No files matched {args.pattern} in {in_dir}", file=sys.stderr)
        return 2

    # Write JSONL atomically
    tmp_index = out_index.with_suffix(out_index.suffix + ".tmp")

    n_written = 0
    n_skipped = 0

    index_lines = []

    for src in files:
        sha = compute_sha256(src)
        shard = sha[: args.shard_len]

        prof_id = pick_profile_id(src, args.id_mode, sha)
        ext = normalize_ext(src, keep_ext=args.keep_ext, forced_ext=args.ext)

        # Output filename: if id-mode=name, keep the full name; else id + ext
        if args.id_mode == "name":
            out_name = prof_id  # includes extension already
            # If user forced ext and id_mode=name, override suffix
            if args.ext is not None:
                out_name = Path(out_name).with_suffix(ext).name
        else:
            out_name = f"{prof_id}{ext}"

        relpath = str(Path(shard) / out_name)
        dst = out_root / relpath

        # collision handling
        dst2 = resolve_collision(dst, args.collision, sha)
        if dst2.exists() and args.collision == "skip":
            n_skipped += 1
            continue

        rec = {
            "id": prof_id,
            "relpath": str(dst2.relative_to(out_root)),
            "sha256": sha,
            "bytes": src.stat().st_size,
            "src_name": src.name,
        }

        if args.dry_run:
            print(f"[DRY] {src} -> {dst2} ({args.mode})")
            index_lines.append(json.dumps(rec))
            n_written += 1
            continue

        safe_mkdir(dst2.parent)

        # If dedup reused existing file, don't rewrite it
        if dst2.exists():
            # exists only in dedup case with same sha
            pass
        else:
            try:
                link_or_copy(src, dst2, args.mode)
            except OSError as e:
                raise RuntimeError(
                    f"Failed to place file ({args.mode}):\n  src={src}\n  dst={dst2}\n  err={e}"
                ) from e

        index_lines.append(json.dumps(rec))
        n_written += 1

    if args.dry_run:
        print(f"\n[DRY] Would write index: {out_index}")
        print(f"[DRY] Profiles indexed: {n_written}, skipped: {n_skipped}")
        return 0

    # Atomic write index
    tmp_index.write_text("\n".join(index_lines) + ("\n" if index_lines else ""))
    tmp_index.replace(out_index)

    print(f"OK: wrote sharded profiles under: {out_root}")
    print(f"OK: wrote index: {out_index}")
    print(f"OK: profiles indexed: {n_written}, skipped: {n_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
