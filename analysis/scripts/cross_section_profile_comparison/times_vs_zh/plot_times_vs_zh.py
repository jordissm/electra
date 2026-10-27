#!/usr/bin/env python3
"""Compare charged-hadron mean production and formation times vs z_h."""

import argparse
import math
from pathlib import Path

SELECTION = "HERMES_2007_FIG2_ZH_CHARGED_TIMES_V1"
BASE = "/HERMES_2007/zh"
COMPARISON_KEYS = ("Selection", "TimeDefinition", "TimeUnit", "Weighting", "Species",
                   "ProductionStatus", "Acceptance", "BeamEnergyGeV", "BeamDirection")


def read_profiles(path):
    profiles = {}
    current = None
    table = False
    with Path(path).open() as stream:
        for line in stream:
            line = line.strip()
            if line.startswith("BEGIN "):
                if current is not None:
                    raise ValueError(f"{path}: nested YODA block")
                kind, name = line.split()[1:]
                if kind == "YODA_PROFILE1D_V2":
                    if name in profiles:
                        raise ValueError(f"{path}: duplicate YODA path {name}")
                    current = {"bins": [], "annotations": {}}
                    profiles[name] = current
                table = False
            elif line.startswith("END "):
                if current is not None and line != "END YODA_PROFILE1D_V2":
                    raise ValueError(f"{path}: mismatched YODA profile end")
                current = None
            elif current is not None:
                if line == "---":
                    table = True
                elif not table and ":" in line:
                    key, value = line.split(":", 1)
                    current["annotations"][key] = value.strip()
                elif table and line and not line.startswith("#"):
                    fields = line.split()
                    if fields[0] in ("Total", "Underflow", "Overflow"):
                        continue
                    if len(fields) != 9:
                        raise ValueError(f"{path}: expected nine Profile1D bin columns")
                    current["bins"].append(tuple(map(float, fields)))
    if current is not None:
        raise ValueError(f"{path}: unterminated YODA profile")
    return profiles


def load_sample(path):
    path = Path(path)
    profiles = read_profiles(path)
    try:
        production = profiles[f"{BASE}/production_time_charged"]
        formation = profiles[f"{BASE}/formation_time_charged"]
    except KeyError as error:
        raise ValueError(f"{path}: missing {error.args[0]}; regenerate with the current utils/analyze_oscar_output.cpp") from error
    metadata = production["annotations"].copy()
    for profile in (production, formation):
        annotations = profile["annotations"]
        if annotations.get("TimeColumns", "complete") != "complete":
            raise ValueError(f"{path}: time profiles are unavailable or partial because input events lack named time/status columns")
        if any(key not in annotations for key in COMPARISON_KEYS):
            raise ValueError(f"{path}: missing time-profile selection annotations")
        if annotations.get("Type") != "Profile1D" or any(annotations[key] != metadata[key] for key in COMPARISON_KEYS):
            raise ValueError(f"{path}: inconsistent production/formation annotations")
    expected = {"Selection": SELECTION, "TimeDefinition": "StoredOSCARCoordinateTime", "TimeUnit": "fm/c",
                "Weighting": "UnitPerChargedHadron", "Species": "-2212 -321 -211 211 321 2212", "ProductionStatus": "1"}
    if any(metadata[key] != value for key, value in expected.items()):
        raise ValueError(f"{path}: incompatible charged-hadron time definition or selection")
    metadata["BeamEnergyGeV"] = float(metadata["BeamEnergyGeV"])
    if not production["bins"] or len(production["bins"]) != len(formation["bins"]):
        raise ValueError(f"{path}: missing bins or mismatched production/formation bin counts")
    rows = []
    for prod, form in zip(production["bins"], formation["bins"]):
        if not all(math.isfinite(value) for value in (*prod, *form)):
            raise ValueError(f"{path}: non-finite raw profile moments")
        lo, hi, count, sumw2, sumz, _, _, _, entries = prod
        if prod[:6] != form[:6] or entries != form[8] or count < 0 or count != int(count) or count != entries or sumw2 != count:
            raise ValueError(f"{path}: mismatched shared hadron counts or unit-weight moments")
        if count == 0 and any((*prod[4:], *form[4:])):
            raise ValueError(f"{path}: empty profile bin has nonzero moments")
        if lo >= hi or (rows and lo != rows[-1]["zh_high"]):
            raise ValueError(f"{path}: invalid or non-contiguous bin edges")
        rows.append({"zh_low": lo, "zh_high": hi, "count": count,
                     "zh_mean": sumz / count if count else math.nan,
                     "production_mean_fm_c": prod[6] / count if count else math.nan,
                     "formation_mean_fm_c": form[6] / count if count else math.nan})
    metadata["zh_edges"] = [row["zh_low"] for row in rows] + [rows[-1]["zh_high"]]
    return rows, metadata


def plot_samples(paths, labels, output_dir, filename="charged_hadron_times_vs_zh", title=""):
    if not paths or len(paths) != len(labels):
        raise ValueError("Supply one label per input YODA file")
    samples = [load_sample(path) for path in paths]
    reference = samples[0][1]
    for _, metadata in samples[1:]:
        for key in (*COMPARISON_KEYS, "zh_edges"):
            if metadata[key] != reference[key]:
                raise ValueError(f"Cannot overlay samples with different {key}")
    # Reading profiles and --help need only the standard library.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10, 4), sharex=True)
    styles = ("-", "--", "-.", ":")
    for index, ((rows, _), label) in enumerate(zip(samples, labels)):
        xs = [(row["zh_low"] + row["zh_high"]) / 2 for row in rows]
        for axis, quantity in zip(axes, ("production", "formation")):
            values = [row[f"{quantity}_mean_fm_c"] if row["count"] else math.nan for row in rows]
            axis.plot(xs, values, marker="o", markersize=3, color=f"C{index % 10}",
                      linestyle=styles[(index // 10) % len(styles)], label=label)
    for axis, quantity in zip(axes, ("production", "formation")):
        axis.set(xlabel=r"$z_h$", ylabel=rf"Mean {quantity} time [fm/$c$]",
                 xlim=(reference["zh_edges"][0], reference["zh_edges"][-1]))
        axis.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    figure.suptitle(title or r"Charged hadrons: $\pi^\pm$, $K^\pm$, $p$, $\bar{p}$")
    figure.tight_layout()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    try:
        for extension in ("pdf", "png"):
            path = output_dir / f"{Path(filename).stem}.{extension}"
            figure.savefig(path, dpi=180)
            outputs.append(path)
            print(f"Wrote {path}")
    finally:
        plt.close(figure)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True, help="Combined YODA files from analyze_oscar_output")
    parser.add_argument("--labels", nargs="+", help="One legend label per input (default: YODA filename stem)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-filename", default="charged_hadron_times_vs_zh")
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    plot_samples(args.inputs, args.labels or [Path(p).stem for p in args.inputs],
                 args.output_dir, args.output_filename, args.title)


if __name__ == "__main__":
    main()
