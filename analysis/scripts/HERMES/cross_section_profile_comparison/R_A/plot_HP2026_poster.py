#!/usr/bin/env python3
import argparse
import os

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

from plot_RA_vs_zh import (
    full_hist_path,
    load_sim_ra,
    load_yaml_config,
    scenario_defs_from_config,
)
from plot_inputs import warn_skip

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Plot Xe proton and anti-proton R_A(z_h) cross-section profile comparisons "
            "for the HP2026 poster."
        )
    )
    ap.add_argument(
        "--config",
        default=os.path.join(SCRIPT_DIR, "RA_vs_zh_inputs.yaml"),
        help="YAML/JSON config listing the deuterium and nuclear YODA files.",
    )
    ap.add_argument(
        "--data-dir",
        default=None,
        help=argparse.SUPPRESS,
    )
    ap.add_argument(
        "--output-dir",
        default=os.path.abspath(
            os.path.join(
                SCRIPT_DIR,
                "..",
                "..",
                "..",
                "..",
                "output",
                "plots",
                "HERMES",
                "cross_section_profile_comparison",
                "R_A",
            )
        ),
        help="Directory for output figures.",
    )
    ap.add_argument(
        "--output-filename",
        default="HP2026_poster.pdf",
        help="Output image filename. Both PDF and PNG are written using its stem.",
    )
    ap.add_argument(
        "--hist-base",
        default=None,
        help="Override histogram base path from the config.",
    )
    ap.add_argument(
        "--hist-pattern",
        default=None,
        help="Override histogram pattern from the config.",
    )
    ap.add_argument("--raw", action="store_true", help="Use RAW histogram paths.")
    ap.add_argument(
        "--no-errorbars", action="store_true", help="Disable simulation bands."
    )
    ap.add_argument("--xlim", nargs=2, type=float, default=(0.05, 1.35))
    ap.add_argument("--ylim", nargs=2, type=float, default=(-0.2, 1.7))
    ap.add_argument(
        "--figsize",
        nargs=2,
        type=float,
        default=(8.8, 4.0),
        metavar=("WIDTH", "HEIGHT"),
        help="Figure size in inches.",
    )
    ap.add_argument(
        "--frame-linewidth",
        type=float,
        default=0.45,
        help="Line width for subplot frames/spines.",
    )
    ap.add_argument("--title", default="", help="Optional suptitle")

    args = ap.parse_args()

    config_path = os.path.abspath(args.config)
    config_dir = os.path.dirname(config_path)
    config = load_yaml_config(config_path)

    nucleus = "Xe"
    particles = ["p", "pbar"]
    hist_base = args.hist_base or str(
        config.get("histogram_base", "/HERMES_2007/zh/multiplicity")
    )
    hist_pattern = args.hist_pattern or str(
        config.get("histogram_pattern", "{base}_{species}")
    )
    scenarios = scenario_defs_from_config(config, config_dir)

    particle_labels = {
        "p": r"$\boldsymbol{p}$",
        "pbar": r"$\boldsymbol{\bar{p}}$",
    }

    fig, axes = plt.subplots(
        1,
        2,
        figsize=tuple(args.figsize),
        sharex=True,
        sharey=True,
        gridspec_kw={"wspace": 0.0},
    )

    plotted_scenarios = set()
    for ip, (ax, particle) in enumerate(zip(axes, particles)):
        for spine in ax.spines.values():
            spine.set_linewidth(args.frame_linewidth)

        ax.set_xlim(*args.xlim)
        ax.set_ylim(*args.ylim)
        ax.axhline(1.0, color="0.65", linewidth=0.8, zorder=1)
        ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        ax.tick_params(
            axis="both",
            which="major",
            labelsize=13,
            width=args.frame_linewidth,
        )
        ax.tick_params(
            axis="both",
            which="minor",
            labelsize=11,
            width=args.frame_linewidth,
        )
        ax.tick_params(axis="x", which="both", top=True, bottom=True)
        ax.set_xlabel(r"${z_h}$", fontsize=20)
        if ip == 0:
            ax.set_ylabel(r"${R^h_A}$", fontsize=20)
        else:
            ax.tick_params(axis="y", which="both", left=False, right=False, labelleft=False)

        ax.text(
            0.075,
            0.90,
            particle_labels.get(particle, particle),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=18,
        )

        hist_path = full_hist_path(hist_base, hist_pattern, particle, args.raw)
        for scenario in scenarios:
            sim = load_sim_ra(scenario, nucleus, particle, hist_path)
            if sim is None or not sim[0]:
                continue
            sx, sy, se = sim
            plotted_scenarios.add(scenario["label"])
            if not args.no_errorbars:
                ax.fill_between(
                    sx,
                    [max(y - e, args.ylim[0]) for y, e in zip(sy, se)],
                    [min(y + e, args.ylim[1]) for y, e in zip(sy, se)],
                    color=scenario["color"],
                    alpha=0.08,
                    linewidth=0,
                    zorder=2,
                )
            ax.plot(
                sx,
                sy,
                color=scenario["color"],
                linestyle=scenario["linestyle"],
                linewidth=2.0,
                zorder=3,
            )

    if not plotted_scenarios:
        warn_skip("No available data for HP2026 poster")
        plt.close(fig)
        return

    scenario_handles = [
        Line2D(
            [0],
            [0],
            color=scenario["color"],
            linestyle=scenario["linestyle"],
            linewidth=2.0,
            label=scenario["label"],
        )
        for scenario in scenarios if scenario["label"] in plotted_scenarios
    ]
    axes[0].legend(
        handles=scenario_handles,
        loc="lower left",
        bbox_to_anchor=(0.04, 0.04),
        frameon=False,
        fontsize=13,
        borderaxespad=0.0,
    )

    if args.title:
        fig.suptitle(args.title, fontsize=18)

    plt.tight_layout(rect=(0, 0, 1, 0.95 if args.title else 1))
    fig.subplots_adjust(wspace=0.0)
    os.makedirs(args.output_dir, exist_ok=True)
    output_stem = os.path.splitext(args.output_filename)[0]
    for ext in (".pdf", ".png"):
        output_path = os.path.join(args.output_dir, output_stem + ext)
        plt.savefig(output_path, dpi=200)
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
