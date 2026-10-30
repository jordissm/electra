#!/usr/bin/env python3
"""Plot HERMES Fig. 2 observables using the analyzer's selected DIS samples."""

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from hermes2007 import load_ratio
from model_comparison.R_A.plot_RA_vs_zh import load_yaml_config, particle_from_description


ROOT = Path(__file__).resolve().parents[3]
AXES = {"nu": (r"$\nu$ [GeV]", (4, 23.5)),
        "zh": (r"$z_h$", (0.1, 1.3)),
        "Q2": (r"$Q^2$ [GeV$^2$]", (1, 25))}
LABELS = {"pip": r"$\pi^+$", "pim": r"$\pi^-$", "pi0": r"$\pi^0$",
          "kp": r"$K^+$", "km": r"$K^-$", "p": r"$p$", "pbar": r"$\bar p$"}


def experimental_points(data_dir, nucleus, axis, species):
    directory = Path(data_dir) / nucleus / f"function_of_{axis}"
    for path in sorted(directory.glob("Table*.csv")):
        text = path.read_text()
        if not any(particle_from_description(line) == species for line in text.splitlines()):
            continue
        rows = csv.reader(line for line in text.splitlines() if line and not line.startswith("#"))
        next(rows)
        return [tuple(map(float, row[:8])) for row in rows if len(row) >= 8]
    raise FileNotFoundError(f"Missing HERMES table: {nucleus}, {species}, {axis} in {directory}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Existing model/cross-section-profile R_A YAML/JSON config")
    parser.add_argument(
        "--comparison", choices=("model", "cross-section-profile", "formation-time"), default="model",
        help="Comparison type; formation-time is a compatibility alias for cross-section-profile.",
    )
    parser.add_argument("--particles", nargs="+", choices=tuple(LABELS), default=["pip", "kp", "p"])
    parser.add_argument("--data-dir", default=str(ROOT / "analysis/experimental_data/HERMES/R_A"))
    parser.add_argument("--no-exp", action="store_true")
    parser.add_argument("--no-errorbars", action="store_true")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-filename", default="RA_fig2.pdf")
    parser.add_argument("--ylim", nargs=2, type=float, default=(0.3, 1.6))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = load_yaml_config(str(config_path))
    if args.comparison in ("cross-section-profile", "formation-time"):
        from cross_section_profile_comparison.R_A.plot_RA_vs_zh import scenario_defs_from_config
    else:
        from model_comparison.R_A.plot_RA_vs_zh import scenario_defs_from_config
    scenarios = scenario_defs_from_config(config, str(config_path.parent))
    nuclei = config.get("nuclei", ["He", "Ne", "Kr", "Xe"])
    colors = {name: f"C{i}" for i, name in enumerate(nuclei)}
    fig, axes = plt.subplots(len(args.particles), 3, squeeze=False,
                             figsize=(11, 2.6 * len(args.particles)), sharey=True)
    plotted = 0
    for ip, species in enumerate(args.particles):
        for column, axis in enumerate(AXES):
            ax = axes[ip, column]
            label, limits = AXES[axis]
            ax.set(xlabel=label, xlim=limits, ylim=args.ylim)
            ax.axhline(1, color="0.7", linewidth=0.7)
            if axis == "Q2":
                ax.set_xscale("log")
                ax.set_xticks([1, 2, 4, 8, 25], ["1", "2", "4", "8", "25"])
            if column == 0:
                ax.set_ylabel(r"$R_A^h$" + "  " + LABELS[species])
            if ip == 0:
                cut = {"nu": r"$z_h>0.2$", "zh": r"$\nu>6$ GeV", "Q2": r"$\nu>6$ GeV, $z_h>0.2$"}[axis]
                ax.set_title(cut, fontsize=10)
            for nucleus in nuclei:
                points = [] if args.no_exp else experimental_points(args.data_dir, nucleus, axis, species)
                # Plot a bin average at the paper's quoted mean, including its wide last bin.
                positions = {round((row[1] + row[2]) / 2, 8): row[0] for row in points}
                for scenario in scenarios:
                    nucleus_file = scenario["nuclei"].get(nucleus)
                    if not nucleus_file:
                        raise ValueError(f"Scenario {scenario['label']} has no {nucleus} input")
                    x, y, error = load_ratio(nucleus_file, scenario["deuterium"], axis, species)
                    x = [positions.get(round(value, 8), value) for value in x]
                    if not x:
                        continue
                    plotted += 1
                    ax.plot(x, y, color=colors[nucleus], linestyle=scenario["linestyle"], linewidth=1.2)
                    if not args.no_errorbars:
                        ax.fill_between(x, [v - e for v, e in zip(y, error)],
                                        [v + e for v, e in zip(y, error)], color=colors[nucleus], alpha=0.1)
                if points:
                    ax.errorbar([r[0] for r in points], [r[3] for r in points],
                                yerr=[max(abs(r[4]), abs(r[5])) for r in points],
                                fmt="o", markersize=3, color=colors[nucleus], linewidth=0.7)
                    ax.errorbar([r[0] for r in points], [r[3] for r in points],
                                yerr=[math.hypot(max(abs(r[4]), abs(r[5])), max(abs(r[6]), abs(r[7]))) for r in points],
                                fmt="none", color=colors[nucleus], linewidth=0.5, capsize=2)
    if not plotted:
        raise ValueError("No ratios have a populated DIS bin and nonzero deuterium yield")
    handles = [Line2D([], [], color=colors[n], label=n) for n in nuclei]
    handles += [Line2D([], [], color="black", linestyle=s["linestyle"], label=s["label"]) for s in scenarios]
    fig.legend(handles=handles, loc="lower center", ncol=min(4, len(handles)), fontsize=9)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for extension in (".pdf", ".png"):
        path = output / (Path(args.output_filename).stem + extension)
        fig.savefig(path, dpi=180)
        print(f"Wrote: {path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
