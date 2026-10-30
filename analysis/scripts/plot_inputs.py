"""Skip unavailable plot inputs while retaining validation of existing data."""

from pathlib import Path
import sys


class MissingDataError(ValueError):
    """A requested histogram or sample has not been supplied."""


_warnings = set()


def warn_skip(message):
    if message not in _warnings:
        print(f"[warn] {message}; skipping.", file=sys.stderr)
        _warnings.add(message)


def optional_data(loader, *args, **kwargs):
    try:
        return loader(*args, **kwargs)
    except (FileNotFoundError, MissingDataError) as error:
        warn_skip(str(error))
        return None


def available_file(filename):
    path = Path(filename)
    if not path.is_file() or path.stat().st_size == 0:
        warn_skip(f"Missing or empty input: {path}")
        return False
    return True
