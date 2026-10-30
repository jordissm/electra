#!/usr/bin/env python3
"""CLAS Fig. 1 pion multiplicity ratios in the HERMES profile-comparison style."""

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import AutoMinorLocator, MaxNLocator, MultipleLocator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from clas2021 import load_ratio

SCRIPT_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = SCRIPT_DIR.parents[3]
NUCLEI = ("C", "Fe", "Pb")
PARTICLES = ("pip", "pim")
LABELS = {"pip": r"$\boldsymbol{\pi^+}$", "pim": r"$\boldsymbol{\pi^-}$"}
# Match the existing HERMES GP profile colors and line styles.
PROFILE_STYLES = {
    "000000": ("Early formation", "darkorange", (0, (7, 2, 1, 2, 1, 2))),
    "000001": ("Profile A", "blue", "-."),
    "000002": ("Profile B", "red", ":"),
    "000003": ("Profile C", "purple", "--"),
    "000004": ("Mean", "green", "-"),
    "000005": ("Late formation", "saddlebrown", (0, (7, 3))),
}


def load_experiment(filename):
    points = {(particle, nucleus): [] for particle in PARTICLES for nucleus in NUCLEI}
    with open(filename, newline="") as stream:
        rows = csv.DictReader(line for line in stream if not line.startswith("#"))
        for row in rows:
            key = row["particle"], row["nucleus"]
            lo, hi, value, stat, syst = (float(row[k]) for k in ("z_low", "z_high", "R", "stat", "sys"))
            if not all(math.isfinite(v) for v in (lo, hi, value, stat, syst)) or lo >= hi or min(stat, syst) < 0:
                raise ValueError(f"Invalid CLAS experimental row: {row}")
            points[key].append((lo, hi, value, stat, syst))
    for key, values in points.items():
        values.sort()
        if not values or any(a[1] > b[0] for a, b in zip(values, values[1:])):
            raise ValueError(f"Missing or overlapping CLAS bins for {key}")
    return points


def load_scenarios(filename):
    if filename is None:
        return []
    filename = Path(filename).resolve()
    try:
        import yaml
    except ModuleNotFoundError:
        config = json.loads(filename.read_text())
    else:
        config = yaml.safe_load(filename.read_text())
    if not isinstance(config, dict):
        raise ValueError("CLAS plot config must be a mapping")
    if config.get("nuclei", list(NUCLEI)) != list(NUCLEI) or config.get("particles", list(PARTICLES)) != list(PARTICLES):
        raise ValueError("CLAS pion plots require nuclei [C, Fe, Pb] and particles [pip, pim]")

    def resolve(value):
        path = Path(os.path.expandvars(value)).expanduser()
        return path if path.is_absolute() else filename.parent / path

    entries = config.get("scenarios")
    if entries is None and "profile_directory" in config:
        directory = resolve(config["profile_directory"])
        paths = sorted((directory / "d").glob("profile_*.yoda"))
        paths = [p for p in paths if p.stat().st_size > 0]
        if not paths:
            raise ValueError(f"No nonempty profile_*.yoda files in {directory / 'd'}; omit --config for data alone")
        entries = [{"deuterium": str(p.resolve()),
                    "nuclei": {n: str((directory / n / p.name).resolve()) for n in NUCLEI}} for p in paths]
    if not isinstance(entries, list):
        raise ValueError("Config must define a profile_directory or scenarios list")
    scenarios = []
    for i, entry in enumerate(entries):
        deuterium = resolve(entry["deuterium"])
        pid = deuterium.stem.removeprefix("profile_")
        label, color, linestyle = PROFILE_STYLES.get(pid, (deuterium.stem, f"C{i % 10}", "-"))
        nuclei = {n: resolve(entry["nuclei"][n]) for n in NUCLEI}
        for path in [deuterium, *nuclei.values()]:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Missing or empty CLAS input: {path}")
        scenarios.append({"deuterium": deuterium, "nuclei": nuclei,
                          "label": entry.get("label", label), "color": entry.get("color", color),
                          "linestyle": entry.get("linestyle", linestyle)})
    return scenarios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="YAML/JSON profile_directory or scenarios config; omit for experimental data alone")
    parser.add_argument("--data-dir", type=Path, default=ANALYSIS_DIR / "experimental_data/CLAS/R_A")
    parser.add_argument("--output-dir", type=Path, default=ANALYSIS_DIR / "output/CLAS/cross_section_profile_comparison/R_A")
    parser.add_argument("--output-filename", default="RA_vs_zh.pdf", help="Both PDF and PNG are written using this stem")
    parser.add_argument("--no-exp", action="store_true", help="Plot simulation only (requires --config)")
    parser.add_argument("--no-errorbars", action="store_true", help="Disable simulation uncertainty bands")
    parser.add_argument("--xlim", nargs=2, type=float, default=(0.0, 1.05))
    parser.add_argument("--ylim", nargs=2, type=float, default=(0.0, 1.4))
    parser.add_argument("--figsize", nargs=2, type=float, default=(7.2, 4.8))
    parser.add_argument("--frame-linewidth", type=float, default=0.3)
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    if args.no_exp and not args.config:
        parser.error("--no-exp requires --config")
    scenarios = load_scenarios(args.config)
    if args.no_exp and not scenarios:
        parser.error("--no-exp requires at least one simulation scenario")
    experiment = {} if args.no_exp else load_experiment(args.data_dir / "TableII.csv")

    fig, axes = plt.subplots(2, 3, squeeze=False, figsize=args.figsize,
                             gridspec_kw={"wspace": 0, "hspace": 0})
    data_handle = None
    for row, particle in enumerate(PARTICLES):
        for column, nucleus in enumerate(NUCLEI):
            ax = axes[row, column]
            ax.set(xlim=args.xlim, ylim=args.ylim)
            for spine in ax.spines.values():
                spine.set_linewidth(args.frame_linewidth)
            ax.axhline(1, color="0.65", linewidth=0.8, zorder=1)
            # Suppress duplicate labels where the adjoining frames meet.
            ax.xaxis.set_major_locator(MultipleLocator(0.2))
            ax.set_xticks([x for x in ax.get_xticks() if args.xlim[0] <= x <= args.xlim[1]
                           and not (column and math.isclose(x, args.xlim[0], abs_tol=1e-10))])
            ax.xaxis.set_minor_locator(AutoMinorLocator(2))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=7, prune="upper" if row else None))
            ax.yaxis.set_minor_locator(AutoMinorLocator(2))
            ax.tick_params(which="both", labelsize=8, width=args.frame_linewidth, top=True)
            if row == 0:
                ax.set_title(nucleus, fontsize=14, fontweight="bold", pad=5)
                ax.tick_params(labelbottom=False)
            else:
                ax.set_xlabel(r"$z_h$", fontsize=14)
            if column == 0:
                ax.set_ylabel(r"$R^h_A$", fontsize=14)
                ax.text(.075, .98, LABELS[particle], transform=ax.transAxes, va="top", fontsize=10)
            else:
                ax.tick_params(axis="y", which="both", left=False, labelleft=False)
            for scenario in scenarios:
                x, y, error = load_ratio(scenario["nuclei"][nucleus], scenario["deuterium"], particle)
                if not x:
                    raise ValueError(f"No populated CLAS ratio bins for {scenario['label']}, {nucleus}, {particle}")
                if not args.no_errorbars:
                    ax.fill_between(x, [v - e for v, e in zip(y, error)], [v + e for v, e in zip(y, error)],
                                    color=scenario["color"], alpha=.08, linewidth=0, zorder=2)
                ax.plot(x, y, color=scenario["color"], linestyle=scenario["linestyle"], linewidth=1.1, zorder=3)
            points = experiment.get((particle, nucleus), [])
            for lo, hi, value, stat, syst in points:
                ax.add_patch(Rectangle((lo, value - syst), hi - lo, 2 * syst, facecolor="0.75",
                                       edgecolor="black", alpha=.35, linewidth=.55, zorder=8))
            if points:
                data_handle = ax.errorbar([(p[0] + p[1]) / 2 for p in points], [p[2] for p in points],
                            yerr=[p[3] for p in points], fmt="o", linestyle="none", color="black",
                            elinewidth=.45, capsize=1.2, capthick=.45, markersize=2.8,
                            markeredgewidth=.45, zorder=10)

    handles = [Line2D([], [], color=s["color"], linestyle=s["linestyle"], linewidth=1.1, label=s["label"])
               for s in scenarios]
    labels = [s["label"] for s in scenarios]
    if data_handle is not None:
        handles.append((Patch(facecolor="0.75", edgecolor="black", alpha=.35), data_handle))
        labels.append("CLAS")
    axes[0, 0].legend(handles=handles, labels=labels, loc="lower left", bbox_to_anchor=(.03, .03),
                      frameon=False, fontsize=8, handlelength=3, borderaxespad=0,
                      handler_map={tuple: HandlerTuple(ndivide=1, pad=0)})
    if args.title:
        fig.suptitle(args.title, fontsize=12)
    fig.subplots_adjust(left=.09, right=.98, bottom=.13,
                        top=.89 if args.title else .94)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for extension in (".pdf", ".png"):
        path = args.output_dir / (Path(args.output_filename).stem + extension)
        fig.savefig(path, dpi=200)
        print(f"Wrote: {path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
