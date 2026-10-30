#!/usr/bin/env python3
"""EMC charged-hadron R_A(z_h): EMC Fig. 4 / eHIJING Fig. 18, C/Cu/Sn panels."""

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
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

SCRIPT_DIR = Path(__file__).resolve().parent
ANALYSIS_DIR = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(SCRIPT_DIR.parents[1]))
from emc1991 import load_ratio
from plot_inputs import MissingDataError, available_file, optional_data, warn_skip

NUCLEI = ("C", "Cu", "Sn")
BEAM_MARKERS = {100: "o", 280: "s"}
PROFILE_STYLES = {
    "000000": ("Early formation", "darkorange", (0, (7, 2, 1, 2, 1, 2))),
    "000001": ("Profile A", "blue", "-."),
    "000002": ("Profile B", "red", ":"),
    "000003": ("Profile C", "purple", "--"),
    "000004": ("Mean", "green", "-"),
    "000005": ("Late formation", "saddlebrown", (0, (7, 3))),
}


def load_experiment(filename):
    if not filename.is_file():
        raise FileNotFoundError(f"Missing EMC data: {filename}. Supply the original EMC table as CSV; see analysis/scripts/README.md")
    if filename.stat().st_size == 0:
        raise MissingDataError(f"Empty EMC data: {filename}")
    points = {n: [] for n in NUCLEI}
    with filename.open(newline="") as stream:
        reader = csv.DictReader(line for line in stream if not line.startswith("#"))
        if not {"nucleus", "z", "R"}.issubset(reader.fieldnames or []):
            raise ValueError("EMC CSV requires nucleus,z,R and error or stat,sys columns")
        for row in reader:
            nucleus = row["nucleus"].strip()
            if nucleus not in points:
                raise ValueError(f"Unknown EMC nucleus: {nucleus}")
            z, y = float(row["z"]), float(row["R"])
            if row.get("error", "").strip():
                if row.get("stat", "").strip() or row.get("sys", "").strip():
                    raise ValueError("Provide either the quoted error or separate stat/sys, not both")
                error, syst = float(row["error"]), None
            else:
                error, syst = float(row["stat"]), float(row["sys"])
            values = [z, y, error] + ([] if syst is None else [syst])
            if not all(math.isfinite(v) for v in values) or error < 0 or (syst is not None and syst < 0):
                raise ValueError(f"Invalid EMC measurement: {row}")
            lo, hi = row.get("z_low", "").strip(), row.get("z_high", "").strip()
            if bool(lo) != bool(hi):
                raise ValueError("Supply both EMC z bin bounds or leave both blank")
            span = (float(lo), float(hi)) if lo else None
            if span and not (math.isfinite(span[0]) and math.isfinite(span[1]) and span[0] < span[1] and span[0] <= z <= span[1]):
                raise ValueError(f"Invalid EMC z interval: {row}")
            beam_text = row.get("beam_energy", "").strip()
            beam = float(beam_text) if beam_text else None
            if beam is not None and beam not in BEAM_MARKERS:
                raise ValueError("EMC Fig. 18 beam_energy must be 100 or 280 GeV, or blank if unspecified")
            points[nucleus].append((z, span, y, error, syst, beam))
    for nucleus, values in points.items():
        if not values:
            warn_skip(f"No EMC measurements supplied for {nucleus}")
        values.sort(key=lambda p: (p[0], p[5] or 0))
    if not any(points.values()):
        raise MissingDataError(f"No EMC measurements supplied in {filename}")
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
        raise ValueError("EMC plot config must be a mapping")

    def resolve(value):
        path = Path(os.path.expandvars(value)).expanduser()
        return path if path.is_absolute() else filename.parent / path

    entries = config.get("scenarios")
    if entries is None and "profile_directory" in config:
        directory = resolve(config["profile_directory"])
        groups = {}
        for beam in (100, 280):
            for deuterium in sorted((directory / str(beam) / "d").glob("profile_*.yoda")):
                if deuterium.stat().st_size == 0:
                    continue
                for nucleus in NUCLEI:
                    nuclear = directory / str(beam) / nucleus / deuterium.name
                    if nuclear.is_file() and nuclear.stat().st_size:
                        groups.setdefault(deuterium.stem, []).append({"nucleus": nucleus,
                            "nuclear": str(nuclear.resolve()), "deuterium": str(deuterium.resolve())})
        entries = [{"samples": samples} for samples in groups.values()]
        if not entries:
            warn_skip(f"No matching nonempty EMC target/deuterium profiles in {directory}/{{100,280}}")
    if not isinstance(entries, list):
        raise ValueError("EMC config requires profile_directory or scenarios")
    scenarios = []
    for i, entry in enumerate(entries):
        samples = []
        for sample in entry["samples"]:
            if sample["nucleus"] not in NUCLEI:
                raise ValueError("EMC scenario nucleus must be C, Cu or Sn")
            nuclear, deuterium = resolve(sample["nuclear"]), resolve(sample["deuterium"])
            if not available_file(nuclear) or not available_file(deuterium):
                continue
            samples.append({"nucleus": sample["nucleus"], "nuclear": nuclear, "deuterium": deuterium})
        if not samples:
            continue
        pid = samples[0]["nuclear"].stem.removeprefix("profile_")
        label, color, linestyle = PROFILE_STYLES.get(pid, (f"Scenario {i + 1}", f"C{i % 10}", "-"))
        scenarios.append({"samples": samples, "label": entry.get("label", label),
                          "color": entry.get("color", color), "linestyle": entry.get("linestyle", linestyle)})
    return scenarios


def create_figure(experiment, scenarios, args):
    fig, axes = plt.subplots(1, 3, figsize=args.figsize, squeeze=False, gridspec_kw={"wspace": 0})
    data_handle = None
    has_boxes = False
    has_systematic = False
    beams = set()
    plotted_scenarios = set()
    for column, nucleus in enumerate(NUCLEI):
        ax = axes[0, column]
        ax.set(xlim=args.xlim, ylim=args.ylim, title=nucleus, xlabel=r"$z_h$")
        ax.title.set(fontsize=14, fontweight="bold")
        ax.xaxis.label.set_size(14)
        for spine in ax.spines.values():
            spine.set_linewidth(args.frame_linewidth)
        ax.axhline(1, color="0.65", linewidth=.8, zorder=1)
        ax.xaxis.set_major_locator(MultipleLocator(.2))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        ax.tick_params(which="both", labelsize=8, width=args.frame_linewidth, top=True)
        if column:
            ax.tick_params(axis="y", which="both", left=False, labelleft=False)
        else:
            ax.set_ylabel(r"$R^h_A$", fontsize=14)
            ax.text(.075, .98, r"$\boldsymbol{h^\pm}$", transform=ax.transAxes, va="top", fontsize=10)
        for scenario in scenarios:
            seen_beams = set()
            for sample in scenario["samples"]:
                if sample["nucleus"] != nucleus:
                    continue
                values = optional_data(load_ratio, sample["nuclear"], sample["deuterium"])
                if values is None or not values[1]:
                    continue
                beam, x, y, error = values
                plotted_scenarios.add(scenario["label"])
                if beam in seen_beams:
                    raise ValueError(f"Duplicate {beam} GeV {nucleus} sample in {scenario['label']}; beam/run merging requires explicit normalization")
                seen_beams.add(beam)
                beams.add(beam)
                if not args.no_errorbars:
                    ax.fill_between(x, [v - e for v, e in zip(y, error)], [v + e for v, e in zip(y, error)],
                                    color=scenario["color"], alpha=.08, linewidth=0, zorder=2)
                ax.plot(x, y, color=scenario["color"], linestyle=scenario["linestyle"], linewidth=1.1,
                        marker=BEAM_MARKERS[beam], markersize=2.2, markerfacecolor="white", zorder=3)
        for z, span, y, error, syst, beam in experiment.get(nucleus, []):
            if beam is not None:
                beams.add(beam)
            if syst is not None:
                has_systematic = True
                if span:
                    has_boxes = True
                    ax.add_patch(Rectangle((span[0], y - syst), span[1] - span[0], 2 * syst,
                                           facecolor="0.75", edgecolor="black", alpha=.35, linewidth=.55, zorder=8))
                else:
                    ax.errorbar([z], [y], yerr=[syst], fmt="none", color="0.65", elinewidth=3, alpha=.6, zorder=8)
            data_handle = ax.errorbar([z], [y], yerr=[error], fmt=BEAM_MARKERS.get(beam, "o"),
                                     linestyle="none", color="black", elinewidth=.45, capsize=1.2,
                                     capthick=.45, markersize=2.8, markeredgewidth=.45, zorder=10)
    if data_handle is None and not plotted_scenarios:
        warn_skip("No available data for EMC R_A figure")
        plt.close(fig)
        return None
    scenarios = [s for s in scenarios if s["label"] in plotted_scenarios]
    handles = [Line2D([], [], color=s["color"], linestyle=s["linestyle"], linewidth=1.1) for s in scenarios]
    labels = [s["label"] for s in scenarios]
    if data_handle is not None:
        if has_systematic:
            systematic_handle = (Patch(facecolor="0.75", edgecolor="black", alpha=.35) if has_boxes
                                 else Line2D([], [], color="0.65", linewidth=3, alpha=.6))
            handles.append((systematic_handle, data_handle))
        else:
            handles.append(data_handle)
        labels.append("EMC")
    if len(beams) > 1 or scenarios:
        for beam in sorted(beams):
            handles.append(Line2D([], [], color="black", marker=BEAM_MARKERS[beam], linestyle="none", markersize=3))
            labels.append(rf"$E_\mu={beam:g}$ GeV")
    compact_legend = len(handles) > 6
    axes[0, 0].legend(handles=handles, labels=labels, loc="lower left", bbox_to_anchor=(.03, .03),
                      frameon=False, fontsize=6.5 if compact_legend else 7,
                      ncol=2 if compact_legend else 1, handlelength=2 if compact_legend else 3,
                      columnspacing=.7, handletextpad=.5, labelspacing=.25, borderaxespad=0,
                      handler_map={tuple: HandlerTuple(ndivide=1, pad=0)})
    if args.title:
        fig.suptitle(args.title, fontsize=12)
    fig.subplots_adjust(left=.09, right=.98, bottom=.17, top=.87 if args.title else .92)
    return fig


def main(*, comparison="cross_section_profile_comparison", default_config=None, description=None):
    parser = argparse.ArgumentParser(description=description or __doc__)
    parser.add_argument("--config", default=default_config, help="YAML/JSON profile_directory or scenarios config; --data-only omits simulations")
    parser.add_argument("--data-file", type=Path, default=ANALYSIS_DIR / "experimental_data/EMC/R_A/Fig4.csv")
    parser.add_argument("--output-dir", type=Path, default=ANALYSIS_DIR / f"output/plots/EMC/{comparison}/R_A")
    parser.add_argument("--output-filename", default="RA_vs_zh.pdf")
    data_options = parser.add_mutually_exclusive_group()
    data_options.add_argument("--no-exp", action="store_true", help="Plot simulation alone; requires --config")
    data_options.add_argument("--data-only", action="store_true", help="Plot experimental data without simulation inputs")
    parser.add_argument("--no-errorbars", action="store_true", help="Disable simulation bands")
    parser.add_argument("--xlim", nargs=2, type=float, default=(.05, .85))
    parser.add_argument("--ylim", nargs=2, type=float, default=(.65, 1.35))
    parser.add_argument("--figsize", nargs=2, type=float, default=(7.2, 3.6))
    parser.add_argument("--frame-linewidth", type=float, default=.3)
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    experiment = {} if args.no_exp else (optional_data(load_experiment, args.data_file) or {})
    scenarios = load_scenarios(None if args.data_only else args.config)
    if args.no_exp and not args.config:
        parser.error("--no-exp requires --config")
    fig = create_figure(experiment, scenarios, args)
    if fig is None:
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for extension in (".pdf", ".png"):
        path = args.output_dir / (Path(args.output_filename).stem + extension)
        fig.savefig(path, dpi=200)
        print(f"Wrote: {path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
