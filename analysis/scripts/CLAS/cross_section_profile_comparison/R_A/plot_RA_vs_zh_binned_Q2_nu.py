#!/usr/bin/env python3
"""CLAS Figs. 2-3: separate pion R_A(z_h) figures in Q2 and nu bins."""

import argparse
import csv
import math
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import AutoMinorLocator, MaxNLocator, MultipleLocator

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parents[1]))
sys.path.insert(0, str(SCRIPT_DIR))
from clas2021 import NU_BINS, Q2_BINS, load_ratio
from plot_inputs import optional_data, warn_skip
from plot_RA_vs_zh import ANALYSIS_DIR, LABELS, NUCLEI, PARTICLES, load_scenarios

# Q2 sets the color/marker; the profile comparison retains its line styles.
Q2_STYLES = (("black", "o"), ("tab:blue", "s"), ("tab:red", "^"))


def load_experiment(filename):
    points = {(p, n, iq, inu): [] for p in PARTICLES for n in NUCLEI
              for iq in range(3) for inu in range(3)}
    with open(filename, newline="") as stream:
        for row in csv.DictReader(line for line in stream if not line.startswith("#")):
            iq = Q2_BINS.index((float(row["Q2_low"]), float(row["Q2_high"])))
            inu = NU_BINS.index((float(row["nu_low"]), float(row["nu_high"])))
            key = row["particle"], row["nucleus"], iq, inu
            if key not in points:
                raise ValueError(f"Unknown CLAS sample in {filename}: {key}")
            if all(row[k] == "" for k in ("R", "stat", "sys")):
                continue  # Unpublished Table VIII cells are not zero measurements.
            lo, hi, value, stat, syst = (float(row[k]) for k in ("z_low", "z_high", "R", "stat", "sys"))
            if not all(math.isfinite(v) for v in (lo, hi, value, stat, syst)) or lo >= hi or min(stat, syst) < 0:
                raise ValueError(f"Invalid CLAS experimental row: {row}")
            points[key].append((lo, hi, value, stat, syst))
    for key, values in points.items():
        values.sort()
        if not values:
            warn_skip(f"No CLAS measurements for {key} in {filename}")
        if any(a[1] > b[0] for a, b in zip(values, values[1:])):
            raise ValueError(f"Missing or overlapping CLAS bins for {key}")
    return points


def create_figure(particle, experiment, scenarios, args):
    simulation = {}
    row_maxima = [1.3] * 3
    for inu in range(3):
        for nucleus in NUCLEI:
            for iq in range(3):
                for lo, hi, y, stat, syst in experiment.get((particle, nucleus, iq, inu), []):
                    row_maxima[inu] = max(row_maxima[inu], y + max(stat, syst))
                for index, scenario in enumerate(scenarios):
                    if nucleus not in scenario["nuclei"]:
                        continue
                    values = optional_data(
                        load_ratio, scenario["nuclei"][nucleus], scenario["deuterium"], particle,
                        q2_bin=iq, nu_bin=inu,
                    )
                    if values is None or not values[0]:
                        continue
                    simulation[nucleus, iq, inu, index] = values
                    for y, error in zip(values[1], values[2]):
                        upper = y + error if not args.no_errorbars and math.isfinite(error) else y
                        row_maxima[inu] = max(row_maxima[inu], upper)

    if not simulation and not any(values for key, values in experiment.items() if key[0] == particle):
        warn_skip(f"No available data for CLAS binned {particle} figure")
        return None

    fig, axes = plt.subplots(3, 3, squeeze=False, figsize=args.figsize,
                             gridspec_kw={"wspace": 0, "hspace": 0})
    data_handles = {}
    for inu, (nu_low, nu_high) in enumerate(NU_BINS):
        limits = args.ylim or (0, .2 * math.ceil((row_maxima[inu] + .06) / .2))
        for column, nucleus in enumerate(NUCLEI):
            ax = axes[inu, column]
            ax.set(xlim=args.xlim, ylim=limits)
            for spine in ax.spines.values():
                spine.set_linewidth(args.frame_linewidth)
            ax.axhline(1, color="0.65", linewidth=.8, zorder=1)
            ax.xaxis.set_major_locator(MultipleLocator(.2))
            ax.set_xticks([x for x in ax.get_xticks() if args.xlim[0] <= x <= args.xlim[1]
                           and not (column and math.isclose(x, args.xlim[0], abs_tol=1e-10))])
            ax.xaxis.set_minor_locator(AutoMinorLocator(2))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=7, prune="upper" if inu else None))
            ax.yaxis.set_minor_locator(AutoMinorLocator(2))
            ax.tick_params(which="both", labelsize=8, width=args.frame_linewidth, top=True)
            if inu == 0:
                ax.set_title(nucleus, fontsize=14, fontweight="bold", pad=5)
            if inu < 2:
                ax.tick_params(labelbottom=False)
            else:
                ax.set_xlabel(r"$z_h$", fontsize=14)
            if column == 0:
                ax.set_ylabel(r"$R^h_A$", fontsize=14)
                ax.text(.075, .98, LABELS[particle], transform=ax.transAxes, va="top", fontsize=10)
            else:
                ax.tick_params(axis="y", which="both", left=False, labelleft=False)
            if column == 2:
                ax.text(1.07, .5, rf"${nu_low:g}<\nu<{nu_high:g}$ GeV", rotation=270,
                        transform=ax.transAxes, va="center", ha="center", fontsize=10)

            for iq, (color, marker) in enumerate(Q2_STYLES):
                for index, scenario in enumerate(scenarios):
                    values = simulation.get((nucleus, iq, inu, index))
                    if values is None:
                        continue
                    x, y, error = values
                    if not args.no_errorbars:
                        ax.fill_between(x, [v - e for v, e in zip(y, error)], [v + e for v, e in zip(y, error)],
                                        color=color, alpha=.06, linewidth=0, zorder=2)
                    ax.plot(x, y, color=color, linestyle=scenario["linestyle"], linewidth=1.1, zorder=3)
                points = experiment.get((particle, nucleus, iq, inu), [])
                for lo, hi, value, stat, syst in points:
                    ax.add_patch(Rectangle((lo, value - syst), hi - lo, 2 * syst, facecolor=color,
                                           edgecolor=color, alpha=.14, linewidth=.55, zorder=8))
                if points:
                    data_handles[iq] = ax.errorbar(
                        [(p[0] + p[1]) / 2 for p in points], [p[2] for p in points],
                        yerr=[p[3] for p in points], fmt=marker, linestyle="none", color=color,
                        elinewidth=.45, capsize=1.2, capthick=.45, markersize=2.8,
                        markeredgewidth=.45, zorder=10,
                    )

    handles, labels = [], []
    for iq, (lo, hi) in enumerate(Q2_BINS):
        color, marker = Q2_STYLES[iq]
        if iq in data_handles:
            handles.append((Patch(facecolor=color, edgecolor=color, alpha=.14), data_handles[iq]))
        else:
            handles.append(Line2D([], [], color=color, marker=marker, linestyle="none", markersize=3))
        labels.append(rf"${lo:.1f}<Q^2<{hi:.1f}$ GeV$^2$")
    for index, scenario in enumerate(scenarios):
        if not any(key[3] == index for key in simulation):
            continue
        handles.append(Line2D([], [], color="black", linestyle=scenario["linestyle"], linewidth=1.1))
        labels.append(scenario["label"])
    axes[0, 0].legend(handles=handles, labels=labels, loc="lower left", bbox_to_anchor=(.03, .03),
                      frameon=False, fontsize=7, handlelength=3, borderaxespad=0,
                      handler_map={tuple: HandlerTuple(ndivide=1, pad=0)})
    if args.title:
        fig.suptitle(args.title, fontsize=14, y=.985)
    fig.subplots_adjust(left=.09, right=.93, bottom=.09, top=.93 if args.title else .96)
    return fig


def main(*, comparison="cross_section_profile_comparison", default_config=None, description=None):
    parser = argparse.ArgumentParser(description=description or __doc__)
    parser.add_argument("--config", default=default_config, help="Same CLAS input config as Fig. 1; --data-only omits simulations")
    parser.add_argument("--particles", nargs="+", choices=PARTICLES, default=list(PARTICLES))
    parser.add_argument("--data-dir", type=Path, default=ANALYSIS_DIR / "experimental_data/CLAS/R_A")
    parser.add_argument("--output-dir", type=Path, default=ANALYSIS_DIR / f"output/plots/CLAS/{comparison}/R_A")
    parser.add_argument("--output-filename", default="RA_vs_zh_binned_Q2_nu.pdf",
                        help="Filename stem; _pip/_pim and PDF/PNG extensions are appended")
    data_options = parser.add_mutually_exclusive_group()
    data_options.add_argument("--no-exp", action="store_true", help="Plot simulation only (requires --config)")
    data_options.add_argument("--data-only", action="store_true", help="Plot experimental data without simulation inputs")
    parser.add_argument("--no-errorbars", action="store_true", help="Disable simulation uncertainty bands")
    parser.add_argument("--xlim", nargs=2, type=float, default=(0, 1.05))
    parser.add_argument("--ylim", nargs=2, type=float, help="Override automatic limits shared within each nu row")
    parser.add_argument("--figsize", nargs=2, type=float, default=(7.2, 8.4))
    parser.add_argument("--frame-linewidth", type=float, default=.3)
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    scenarios = load_scenarios(None if args.data_only else args.config)
    if args.no_exp and not args.config:
        parser.error("--no-exp requires --config")
    experiment = {} if args.no_exp else (optional_data(load_experiment, args.data_dir / "TablesIII_VIII.csv") or {})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for particle in dict.fromkeys(args.particles):
        fig = create_figure(particle, experiment, scenarios, args)
        if fig is None:
            continue
        for extension in (".pdf", ".png"):
            path = args.output_dir / (Path(args.output_filename).stem + "_" + particle + extension)
            fig.savefig(path, dpi=200)
            print(f"Wrote: {path}")
        plt.close(fig)


if __name__ == "__main__":
    main()
