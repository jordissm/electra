"""Read CLAS YAML-mode multiplicities; retain the analyzer's event-level errors."""

from functools import lru_cache
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plot_inputs import MissingDataError

Q2_BINS = ((1.0, 1.3), (1.3, 1.8), (1.8, 4.1))
NU_BINS = ((2.2, 3.2), (3.2, 3.7), (3.7, 4.2))


@lru_cache(maxsize=64)
def read_histograms(filename, mtime_ns):
    histograms, provenance = {}, []
    current = None
    table = False
    with open(filename) as stream:
        for line in stream:
            if line.startswith("# YAML | "):
                provenance.append(line.removeprefix("# YAML | "))
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
    return histograms, "".join(provenance)


def spectrum(filename, species, *, q2_bin=None, nu_bin=None):
    path = Path(filename).resolve()
    histograms, provenance = read_histograms(str(path), path.stat().st_mtime_ns)
    sliced = q2_bin is not None or nu_bin is not None
    if sliced:
        if q2_bin not in range(3) or nu_bin not in range(3):
            raise ValueError("Provide both q2_bin and nu_bin, each from 0 to 2")
        histogram_name = "zh_Q2_nu"
        base = f"/CLAS_2021/{histogram_name}/Q2_bin{q2_bin}/nu_bin{nu_bin}"
    else:
        histogram_name = "zh"
        base = "/CLAS_2021/zh"
    name = f"{base}/multiplicity_{species}"
    if name not in histograms:
        raise MissingDataError(f"{filename}: missing {name}; regenerate CLAS YAML analyzer output with {histogram_name}")
    histogram = histograms[name]
    annotations = histogram["annotations"]
    required = {
        "Analysis": "CLAS_2021", "Selection": f"YAML_V1_{histogram_name}", "Axis": "zh",
        "Dimensions": "3" if sliced else "1", "Normalization": "per_DIS",
        "Uncertainty": "EventRatioStandardError",
    }
    if any(annotations.get(k) != v for k, v in required.items()):
        raise ValueError(f"{filename}: expected normalized CLAS YAML multiplicities with event-level errors")
    keys = ("Frame", "Weighting", "BeamEnergyGeV", "BeamMassGeV", "BeamDirection", "DensityAxes")
    if not provenance or any(k not in annotations for k in keys):
        raise ValueError(f"{filename}: missing analysis provenance or beam/frame metadata")
    if sliced:
        for key, variable, bounds in (("Slice1", "Q2", Q2_BINS[q2_bin]), ("Slice2", "nu", NU_BINS[nu_bin])):
            parts = annotations.get(key, "").split()
            if (len(parts) != 3 or parts[0] != variable or
                    not all(math.isclose(float(v), expected, rel_tol=0, abs_tol=1e-12)
                            for v, expected in zip(parts[1:], bounds))):
                raise ValueError(f"{filename}: {key} must match the published {variable} bin {bounds}")
        keys += ("Slice1", "Slice2")
    if not histogram["bins"]:
        raise MissingDataError(f"{filename}: no bins in {name}")
    return histogram["bins"], (provenance, tuple(annotations[k] for k in keys))


def load_ratio(nucleus_file, deuterium_file, species, *, q2_bin=None, nu_bin=None):
    nucleus, nmeta = spectrum(nucleus_file, species, q2_bin=q2_bin, nu_bin=nu_bin)
    deuterium, dmeta = spectrum(deuterium_file, species, q2_bin=q2_bin, nu_bin=nu_bin)
    if nmeta != dmeta:
        raise ValueError("Nucleus and deuterium CLAS analysis definitions or beam/frame metadata differ")
    if [b[:2] for b in nucleus] != [b[:2] for b in deuterium]:
        raise ValueError("Nucleus and deuterium CLAS bin edges differ; interpolation is disabled")
    xs, ratios, errors = [], [], []
    for num, den in zip(nucleus, deuterium):
        lo, hi, a, variance_a = num[:4]
        _, _, d, variance_d = den[:4]
        if not math.isfinite(a) or not math.isfinite(d) or d <= 0:
            continue
        if a < 0 or variance_a < 0 or variance_d < 0:
            raise ValueError("Negative CLAS multiplicity or variance")
        xs.append((lo + hi) / 2)
        ratios.append(a / d)
        errors.append(math.hypot(math.sqrt(variance_a) / d, a * math.sqrt(variance_d) / d**2))
    return xs, ratios, errors
