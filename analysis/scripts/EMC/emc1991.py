"""Read single-energy EMC YAML multiplicities without combining beam samples."""

from functools import lru_cache
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plot_inputs import MissingDataError


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


def spectrum(filename):
    path = Path(filename).resolve()
    histograms, provenance = read_histograms(str(path), path.stat().st_mtime_ns)
    names = [name for name in histograms if re.fullmatch(r"/EMC_(100|280)/zh/multiplicity_charged", name)]
    if not names:
        raise MissingDataError(f"{filename}: missing EMC charged-hadron multiplicity histogram")
    if len(names) != 1:
        raise ValueError(f"{filename}: expected one /EMC_100/zh/multiplicity_charged or /EMC_280/zh/multiplicity_charged histogram")
    name = names[0]
    beam = int(name.split("/")[1].removeprefix("EMC_"))
    histogram = histograms[name]
    annotations = histogram["annotations"]
    required = {"Analysis": f"EMC_{beam}", "Selection": "YAML_V1_zh", "Frame": "TRF",
                "Axis": "zh", "Dimensions": "1", "Normalization": "per_DIS",
                "Uncertainty": "EventRatioStandardError"}
    if any(annotations.get(k) != v for k, v in required.items()):
        raise ValueError(f"{filename}: expected normalized EMC charged-hadron YAML multiplicities in TRF")
    keys = ("Frame", "Weighting", "BeamEnergyGeV", "BeamMassGeV", "BeamDirection", "DensityAxes")
    if not provenance or any(k not in annotations for k in keys):
        raise ValueError(f"{filename}: missing analysis provenance or beam metadata")
    if (not math.isclose(float(annotations["BeamEnergyGeV"]), beam, abs_tol=1e-8) or
            not math.isclose(float(annotations["BeamMassGeV"]), .1056583755, rel_tol=0, abs_tol=1e-8)):
        raise ValueError(f"{filename}: expected a {beam} GeV muon beam")
    if not histogram["bins"]:
        raise MissingDataError(f"{filename}: no bins in {name}")
    return beam, histogram["bins"], (provenance, tuple(annotations[k] for k in keys))


def load_ratio(nucleus_file, deuterium_file):
    beam, nucleus, nmeta = spectrum(nucleus_file)
    dbeam, deuterium, dmeta = spectrum(deuterium_file)
    if beam != dbeam or nmeta != dmeta:
        raise ValueError("EMC nucleus/deuterium beam energies or analysis definitions differ; combining energies is disabled")
    if [b[:2] for b in nucleus] != [b[:2] for b in deuterium]:
        raise ValueError("EMC nucleus/deuterium z bin edges differ; interpolation is disabled")
    xs, ratios, errors = [], [], []
    for num, den in zip(nucleus, deuterium):
        lo, hi, a, va = num[:4]
        _, _, d, vd = den[:4]
        if not math.isfinite(a) or not math.isfinite(d) or d <= 0:
            continue
        if a < 0 or va < 0 or vd < 0:
            raise ValueError("Negative EMC multiplicity or variance")
        xs.append((lo + hi) / 2)
        ratios.append(a / d)
        errors.append(math.hypot(math.sqrt(va) / d, a * math.sqrt(vd) / d**2))
    return beam, xs, ratios, errors
