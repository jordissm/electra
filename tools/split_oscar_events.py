#!/usr/bin/env python3
"""
Split a single OSCAR2013 file containing multiple eHIJING events into
per-event files: evt_XXXXXX.oscar

Event format assumed (as in your sample):
  #!OSCAR2013 ...
  # Units: ...
  # event 1 out ...
  <particle lines>
  # event 1 end ...
  # event 2 out ...
  ...

Behavior:
- Copies the global header (everything before the first "# event ... out ...")
  into each output file.
- Writes each event block including its "# event ... out ..." and "# event ... end ..." lines.
- Streams input (safe for huge files).
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Optional, TextIO


EVENT_OUT_RE = re.compile(r"^\s*#\s*event\s+(\d+)\s+out\b", re.IGNORECASE)
EVENT_END_RE = re.compile(r"^\s*#\s*event\s+(\d+)\s+end\b", re.IGNORECASE)


def mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def open_atomic_for_write(path: Path) -> TextIO:
    """
    Open a temp file next to 'path' and return the file handle.
    Caller must close and then replace.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    # newline="" to preserve line endings consistently
    return open(tmp, "w", encoding="utf-8", newline="")


def finalize_atomic(tmp_path: Path, final_path: Path) -> None:
    tmp_path.replace(final_path)


def split_oscar(
    in_file: Path,
    out_dir: Path,
    *,
    digits: int = 6,
    overwrite: bool = False,
    limit: Optional[int] = None,
    start_event: Optional[int] = None,
    end_event: Optional[int] = None,
) -> int:
    """
    Returns number of events written.
    """
    mkdir(out_dir)

    # Guard: prevent accidentally writing outputs into same directory as input file in-place with same name
    # (Not strictly necessary, but avoids accidental clobbering patterns.)
    if in_file.resolve().parent == out_dir.resolve():
        # It's still safe because filenames differ, but this catches common mistakes.
        pass

    header_lines: list[str] = []
    wrote = 0

    current_event_id: Optional[int] = None
    out_fh: Optional[TextIO] = None
    out_tmp_path: Optional[Path] = None
    out_final_path: Optional[Path] = None

    def close_current_event():
        nonlocal out_fh, out_tmp_path, out_final_path, current_event_id, wrote
        if out_fh is None:
            return
        out_fh.flush()
        out_fh.close()
        assert out_tmp_path is not None and out_final_path is not None
        finalize_atomic(out_tmp_path, out_final_path)
        out_fh = None
        out_tmp_path = None
        out_final_path = None
        current_event_id = None
        wrote += 1

    with open(in_file, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            m_out = EVENT_OUT_RE.match(line)
            m_end = EVENT_END_RE.match(line)

            if current_event_id is None:
                # Not inside an event yet.
                if m_out:
                    evt_id = int(m_out.group(1))

                    # Apply event-range filters
                    if start_event is not None and evt_id < start_event:
                        # Skip this whole event: consume until its end marker
                        # but we need to enter "skip mode"
                        current_event_id = evt_id
                        out_fh = None
                        out_tmp_path = None
                        out_final_path = None
                        # We are "inside event but skipping output" -> handled below.
                        # Still, we should track and ignore lines until end.
                    elif end_event is not None and evt_id > end_event:
                        # We can stop early because events are monotonically increasing in typical files.
                        break
                    else:
                        # Create output file for this event
                        out_final_path = out_dir / f"evt_{evt_id:0{digits}d}.oscar"
                        if out_final_path.exists() and not overwrite:
                            raise FileExistsError(
                                f"Refusing to overwrite existing file: {out_final_path} "
                                f"(use --overwrite to allow)."
                            )
                        out_tmp_path = out_final_path.with_suffix(out_final_path.suffix + ".tmp")
                        out_fh = open(out_tmp_path, "w", encoding="utf-8", newline="")

                        # Write header + the event out line
                        for hl in header_lines:
                            out_fh.write(hl)
                        out_fh.write(line)

                        current_event_id = evt_id

                else:
                    # Still header region; collect
                    header_lines.append(line)
                continue

            # If we’re here, we are “inside an event” (either writing it, or skipping it)
            assert current_event_id is not None

            # If this is a new "# event X out" while still inside an event -> malformed
            if m_out:
                new_evt = int(m_out.group(1))
                raise ValueError(
                    f"{in_file}:{lineno} Found new event start (event {new_evt}) "
                    f"before ending previous event {current_event_id}. "
                    "Input file is malformed or missing an '# event ... end ...' line."
                )

            # Write line if we are not skipping
            if out_fh is not None:
                out_fh.write(line)

            if m_end:
                end_evt = int(m_end.group(1))
                if end_evt != current_event_id:
                    raise ValueError(
                        f"{in_file}:{lineno} Event end id ({end_evt}) does not match "
                        f"current event id ({current_event_id})."
                    )

                # Close event (or finish skipping)
                if out_fh is not None:
                    close_current_event()
                else:
                    # We were skipping output for this event
                    current_event_id = None

                # Stop if we've reached a limit
                if limit is not None and wrote >= limit:
                    break

    # If file ended while still inside an event and writing, that's an error
    if out_fh is not None or current_event_id is not None:
        raise ValueError(
            f"{in_file}: EOF reached while still inside event {current_event_id} "
            "(missing '# event ... end ...'?)"
        )

    return wrote


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="split_oscar_events.py",
        description="Split a multi-event OSCAR2013 file into evt_XXXXXX.oscar per event.",
    )
    ap.add_argument("--in-file", required=True, help="Path to the input multi-event OSCAR file.")
    ap.add_argument("--out-dir", required=True, help="Directory to write evt_XXXXXX.oscar files.")
    ap.add_argument("--digits", type=int, default=6, help="Zero-padding digits for event filenames (default: 6).")
    ap.add_argument("--overwrite", action="store_true", help="Allow overwriting existing output files.")
    ap.add_argument("--limit", type=int, default=None, help="Optional: stop after writing this many events.")
    ap.add_argument("--start-event", type=int, default=None, help="Optional: only write events >= this id.")
    ap.add_argument("--end-event", type=int, default=None, help="Optional: only write events <= this id.")

    args = ap.parse_args()

    in_file = Path(args.in_file).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not in_file.exists():
        raise SystemExit(f"ERROR: input file does not exist: {in_file}")
    if not in_file.is_file():
        raise SystemExit(f"ERROR: input path is not a file: {in_file}")

    wrote = split_oscar(
        in_file=in_file,
        out_dir=out_dir,
        digits=args.digits,
        overwrite=args.overwrite,
        limit=args.limit,
        start_event=args.start_event,
        end_event=args.end_event,
    )

    print(f"Wrote {wrote} event files into: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
