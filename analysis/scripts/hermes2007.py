"""Read the analyzer's Fig. 2 event counts and form bin-aligned multiplicity ratios."""

from functools import lru_cache
import math
from pathlib import Path


SELECTION = "HERMES_2007_FIG2_V1"


@lru_cache(maxsize=64)
def read_histograms(filename, mtime_ns):
    histograms = {}
    current = None
    table = False
    with open(filename) as stream:
        for line in stream:
            if line.startswith("BEGIN YODA_HISTO1D_V2 "):
                current = {"bins": [], "annotations": {}}
                histograms[line.split()[2]] = current
                table = False
            elif line.startswith("END YODA_HISTO1D_V2"):
                current = None
            elif current is not None:
                if line.startswith("# xlow"):
                    table = True
                elif table and line.strip() and not line.startswith("#"):
                    current["bins"].append(tuple(map(float, line.split())))
                elif not table and ":" in line:
                    key, value = line.split(":", 1)
                    current["annotations"][key] = value.strip()
    return histograms


def spectrum(filename, axis, species):
    path = Path(filename).resolve()
    histograms = read_histograms(str(path), path.stat().st_mtime_ns)
    base = f"/HERMES_2007/{axis}"
    try:
        counts = histograms[f"{base}/counts_{species}"]
        dis = histograms[f"{base}/DIS"]
    except KeyError as exc:
        raise ValueError(f"{filename}: missing {exc.args[0]}; rerun analyze_oscar_output.cpp") from exc
    keys = ("Selection", "Acceptance", "BeamEnergyGeV", "BeamDirection")
    metadata = {key: counts["annotations"].get(key) for key in keys}
    dmeta = {key: dis["annotations"].get(key) for key in keys}
    if metadata.get("Selection") != SELECTION or any(v is None for v in metadata.values()) or dmeta != metadata:
        raise ValueError(f"{filename}: missing or inconsistent HERMES selection metadata")
    if len(counts["bins"]) != len(dis["bins"]):
        raise ValueError(f"{filename}: hadron and DIS bin counts differ")
    result = []
    for hadron, denominator in zip(counts["bins"], dis["bins"]):
        lo, hi, total, squared = hadron[:4]
        if (lo, hi) != denominator[:2]:
            raise ValueError(f"{filename}: hadron and DIS bin edges differ")
        n = denominator[2]
        if n <= 0:
            result.append((lo, hi, math.nan, math.nan))
            continue
        width = hi - lo if axis == "zh" else 1.0
        mean = total / n
        # The numerator's second moment is accumulated once per event/bin.
        variance = max(0.0, squared - total * mean) / (n * (n - 1)) if n > 1 else math.nan
        result.append((lo, hi, mean / width, math.sqrt(variance) / width))
    return result, metadata


def load_ratio(nucleus_file, deuterium_file, axis, species):
    nucleus, nmeta = spectrum(nucleus_file, axis, species)
    deuterium, dmeta = spectrum(deuterium_file, axis, species)
    if nmeta != dmeta:
        raise ValueError("Nucleus and deuterium HERMES selection/beam/acceptance metadata differ")
    if len(nucleus) != len(deuterium):
        raise ValueError("Nucleus and deuterium have different histogram bin counts")
    xs, ratios, errors = [], [], []
    for num, den in zip(nucleus, deuterium):
        lo, hi, a, ae = num
        dlo, dhi, d, de = den
        if (lo, hi) != (dlo, dhi):
            raise ValueError("Nucleus and deuterium have different bin edges; interpolation is disabled")
        if not math.isfinite(a) or not math.isfinite(d) or d <= 0:
            continue
        xs.append((lo + hi) / 2)
        ratios.append(a / d)  # Preserve a physical zero numerator.
        errors.append(math.hypot(ae / d, a * de / d**2))
    return xs, ratios, errors
