#!/usr/bin/env python3
import argparse
import csv
import glob
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hermes2007 import load_ratio
from plot_inputs import optional_data, warn_skip

# Match the GP profiles, with distinct styles for the early/late limits.
PROFILE_STYLES = {
    "000000": ("Early formation", "darkorange", (0, (7, 2, 1, 2, 1, 2))),
    "000001": ("Profile A", "blue", "-."),
    "000002": ("Profile B", "red", ":"),
    "000003": ("Profile C", "purple", "--"),
    "000004": ("Mean", "green", "-"),
    "000005": ("Late formation", "saddlebrown", (0, (7, 3))),
}


class DataLegendHandle:
    def __init__(self, filled: bool):
        self.filled = filled


class HandlerDataLegend(HandlerBase):
    def create_artists(
        self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans
    ):
        cx = xdescent + 0.5 * width
        cy = ydescent + 0.5 * height
        box_w = 0.70 * width
        box_h = 0.65 * height
        cap_w = 0.24 * width

        box = Rectangle(
            (cx - 0.5 * box_w, cy - 0.5 * box_h),
            box_w,
            box_h,
            facecolor="0.85",
            edgecolor="black",
            alpha=0.45,
            linewidth=1.0,
            transform=trans,
        )
        err = Line2D(
            [cx, cx],
            [cy - 0.5 * box_h, cy + 0.5 * box_h],
            color="black",
            linewidth=1.2,
            transform=trans,
        )
        cap_low = Line2D(
            [cx - 0.5 * cap_w, cx + 0.5 * cap_w],
            [cy - 0.5 * box_h, cy - 0.5 * box_h],
            color="black",
            linewidth=1.2,
            transform=trans,
        )
        cap_high = Line2D(
            [cx - 0.5 * cap_w, cx + 0.5 * cap_w],
            [cy + 0.5 * box_h, cy + 0.5 * box_h],
            color="black",
            linewidth=1.2,
            transform=trans,
        )
        marker = Line2D(
            [cx],
            [cy],
            marker="o",
            linestyle="none",
            color="black",
            markerfacecolor="black" if orig_handle.filled else "none",
            markeredgecolor="black",
            markersize=4.0,
            transform=trans,
        )
        return [box, err, cap_low, cap_high, marker]


def load_yaml_config(path: str) -> Dict[str, object]:
    with open(path, "r") as f:
        text = f.read()

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ModuleNotFoundError:
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at top level in {path}")
    return data


def resolve_path(path: str, base_dir: str) -> str:
    expanded = os.path.expanduser(os.path.expandvars(path))
    if os.path.isabs(expanded):
        return expanded
    return os.path.abspath(os.path.join(base_dir, expanded))


def parse_yoda_histo1d_v2(path: str, hist_path: str) -> Dict[str, object]:
    in_block = False
    in_table = False
    scaled_by = None
    bins: List[Tuple[float, float, float, float, float, float, float]] = []

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")

            if line.startswith("BEGIN YODA_HISTO1D_V2 "):
                in_block = line.split(" ", 3)[-1].strip() == hist_path
                in_table = False
                continue

            if not in_block:
                continue

            if line.startswith("END YODA_HISTO1D_V2"):
                break

            if line.startswith("ScaledBy:"):
                try:
                    scaled_by = float(line.split(":", 1)[1].strip())
                except Exception:
                    scaled_by = None
                continue

            if line.startswith("# xlow"):
                in_table = True
                continue

            if not in_table or not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 6:
                continue

            xlow = float(parts[0])
            xhigh = float(parts[1])
            sumw = float(parts[2])
            sumw2 = float(parts[3])
            sumwx = float(parts[4])
            sumwx2 = float(parts[5])
            num_entries = float(parts[6]) if len(parts) >= 7 else 0.0
            bins.append((xlow, xhigh, sumw, sumw2, sumwx, sumwx2, num_entries))

    if not bins:
        raise RuntimeError(f"Did not find bins for hist '{hist_path}' in '{path}'")
    return {"scaledBy": scaled_by, "bins": bins}


def build_xy(bins: List[Tuple[float, float, float, float, float, float, float]]):
    xs, ys, yerrs = [], [], []
    for xlow, xhigh, sumw, sumw2, _sumwx, _sumwx2, _num_entries in bins:
        xs.append(0.5 * (xlow + xhigh))
        ys.append(sumw)
        yerrs.append(math.sqrt(sumw2) if sumw2 >= 0 else 0.0)
    return xs, ys, yerrs


def positive_points(xs, ys, yerrs):
    xs_p, ys_p, yerrs_p = [], [], []
    for x, y, ye in zip(xs, ys, yerrs):
        if y > 0 and math.isfinite(y):
            xs_p.append(x)
            ys_p.append(y)
            yerrs_p.append(ye)
    return xs_p, ys_p, yerrs_p


def interpolate_y_and_error(
    xs: List[float], ys: List[float], yerrs: List[float], x: float
) -> Tuple[Optional[float], Optional[float]]:
    if len(xs) < 2 or x < xs[0] or x > xs[-1]:
        return None, None

    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return ys[i], yerrs[i]
            t = (x - x0) / (x1 - x0)
            y = (1.0 - t) * ys[i] + t * ys[i + 1]
            yerr = math.sqrt(((1.0 - t) * yerrs[i]) ** 2 + (t * yerrs[i + 1]) ** 2)
            return y, yerr

    return None, None


def ratio_arrays(
    numerator_xs: List[float],
    numerator_ys: List[float],
    numerator_yerrs: List[float],
    denominator_xs: List[float],
    denominator_ys: List[float],
    denominator_yerrs: List[float],
) -> Tuple[List[float], List[float], List[float]]:
    ratio_xs, ratios, ratio_errs = [], [], []
    for x, num_y, num_err in zip(numerator_xs, numerator_ys, numerator_yerrs):
        den_y, den_err = interpolate_y_and_error(
            denominator_xs, denominator_ys, denominator_yerrs, x
        )
        if den_y is None or num_y <= 0 or den_y <= 0:
            continue
        ratio = num_y / den_y
        ratio_err = ratio * math.sqrt((num_err / num_y) ** 2 + (den_err / den_y) ** 2)
        ratio_xs.append(x)
        ratios.append(ratio)
        ratio_errs.append(ratio_err)
    return ratio_xs, ratios, ratio_errs


def particle_from_description(description: str) -> Optional[str]:
    match = re.search(
        r"description:\s*(PI\+|PI-|K\+|K-|P|PBAR|PI0)\s+multiplic(?:i)?ty",
        description,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "PI+": "pip",
        "PI-": "pim",
        "K+": "kp",
        "K-": "km",
        "P": "p",
        "PBAR": "pbar",
        "PI0": "pi0",
    }[match.group(1).upper()]


def load_ra_points(path: str):
    xs: List[float] = []
    spans: List[Tuple[float, float]] = []
    ys: List[float] = []
    stat_errs: List[float] = []
    sys_errs: List[float] = []
    in_data = False

    with open(path, "r", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            first = row[0].strip()
            if first == "Z":
                in_data = True
                continue
            if first.startswith("#"):
                continue
            if not in_data or len(row) < 8:
                continue
            xs.append(float(row[0]))
            spans.append((float(row[1]), float(row[2])))
            ys.append(float(row[3]))
            stat_errs.append(max(abs(float(row[4])), abs(float(row[5]))))
            sys_errs.append(max(abs(float(row[6])), abs(float(row[7]))))

    if not xs:
        raise RuntimeError(f"No R_A points found in '{path}'")
    return xs, spans, ys, stat_errs, sys_errs


def build_experimental_index(
    data_dir: str, nuclei: List[str]
) -> Dict[Tuple[str, str], str]:
    index: Dict[Tuple[str, str], str] = {}
    for nucleus in nuclei:
        directory = os.path.join(data_dir, nucleus, "function_of_zh")
        if not os.path.isdir(directory):
            print(f"[warn] Missing experimental directory: {directory}")
            continue
        for name in os.listdir(directory):
            if not name.startswith("Table") or not name.endswith(".csv"):
                continue
            path = os.path.join(directory, name)
            particle = None
            with open(path, "r") as f:
                for line in f:
                    particle = particle_from_description(line)
                    if particle is not None:
                        break
            if particle is not None:
                index[(nucleus, particle)] = path
    return index


def formation_time_value(yoda_path: str) -> str:
    base = os.path.splitext(os.path.basename(yoda_path))[0]
    match = re.search(r"tau[=_-](.+)$", base)
    if match:
        return match.group(1)
    return base


def formation_time_label_from_path(yoda_path: str) -> str:
    base = os.path.splitext(os.path.basename(yoda_path))[0]
    if base.startswith("profile_"):
        pid = base[len("profile_"):]
        return PROFILE_STYLES.get(pid, (f"Profile {pid}", "black", "-"))[0]
    value = formation_time_value(yoda_path)
    value_no_units = re.sub(r"fm$", "", value, flags=re.IGNORECASE)
    if value_no_units.lower() in {"inf", "infty", "infinity"}:
        return r"$\tau_\mathrm{form}\to\infty$"
    if value.lower().endswith("fm"):
        return rf"$\tau_\mathrm{{form}}={value_no_units}\,\mathrm{{fm}}$"
    return rf"$\tau_\mathrm{{form}}={value}$"


def scenario_label(scenario: Dict[str, object], deuterium_path: str) -> str:
    label = scenario.get("label")
    if isinstance(label, str) and label:
        if label.startswith("$"):
            return label
        if label.startswith("tau"):
            return formation_time_label_from_path(label + ".yoda")
        return label
    return formation_time_label_from_path(deuterium_path)


def scenario_defs_from_config(config: Dict[str, object], config_dir: str):
    raw_scenarios = config.get("scenarios")
    if raw_scenarios is None and isinstance(config.get("profile_directory"), str):
        profile_dir = resolve_path(config["profile_directory"], config_dir)
        nuclei = config.get("nuclei", ["He", "Ne", "Kr", "Xe"])
        raw_scenarios = []
        paths = set(glob.glob(os.path.join(profile_dir, "d", "profile_*.yoda")))
        paths.update(glob.glob(os.path.join(profile_dir, "d", "tau*.yoda")))
        for deuterium in sorted(paths):
            if os.path.getsize(deuterium) == 0:
                print(f"[warn] Empty deuterium YODA file: {deuterium}; skipping.")
                continue
            filename = os.path.basename(deuterium)
            raw_scenarios.append(
                {
                    "deuterium": deuterium,
                    "nuclei": {
                        nucleus: os.path.join(profile_dir, nucleus, filename)
                        for nucleus in nuclei
                    },
                }
            )
        if not raw_scenarios:
            warn_skip(f"No nonempty profile_*.yoda or tau*.yoda files found in {profile_dir}/d")
    if not isinstance(raw_scenarios, list):
        raise ValueError("Config must define a 'profile_directory' or 'scenarios' list")

    linestyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1)), (0, (5, 1)), (0, (1, 1))]
    colors = [
        "tab:blue",
        "tab:red",
        "tab:green",
        "tab:purple",
        "tab:orange",
        "tab:brown",
    ]
    scenarios = []
    for i, scenario in enumerate(raw_scenarios):
        if not isinstance(scenario, dict):
            raise ValueError("Each scenario entry must be a mapping")
        if not isinstance(scenario.get("deuterium"), str):
            raise ValueError("Each scenario must define a deuterium YODA path")
        nuclei = scenario.get("nuclei")
        if not isinstance(nuclei, dict):
            raise ValueError("Each scenario must define a nuclei mapping")
        deuterium = resolve_path(scenario["deuterium"], config_dir)
        nucleus_paths = {
            str(nucleus): resolve_path(str(path), config_dir)
            for nucleus, path in nuclei.items()
        }
        pid = os.path.splitext(os.path.basename(deuterium))[0].removeprefix("profile_")
        _, default_color, default_linestyle = PROFILE_STYLES.get(
            pid, ("", colors[i % len(colors)], linestyles[i % len(linestyles)])
        )
        scenarios.append(
            {
                "label": scenario_label(scenario, deuterium),
                "linestyle": scenario.get("linestyle", default_linestyle),
                "color": scenario.get("color", default_color),
                "deuterium": deuterium,
                "nuclei": nucleus_paths,
            }
        )
    return scenarios


def full_hist_path(base: str, pattern: str, species: str, raw: bool) -> str:
    hp = pattern.format(base=base, species=species, suf=species)
    if raw and not hp.startswith("/RAW/"):
        hp = "/RAW" + hp
    return hp


def load_sim_ra(scenario, nucleus: str, species: str, hist_path: str):
    deuterium = scenario["deuterium"]
    nucleus_path = scenario["nuclei"].get(nucleus)
    if nucleus_path is None:
        print(f"[warn] Scenario '{scenario['label']}' has no YODA path for {nucleus}")
        return None
    if not os.path.exists(deuterium):
        print(f"[warn] Missing deuterium YODA file: {deuterium}")
        return None
    if not os.path.exists(nucleus_path):
        print(f"[warn] Missing {nucleus} YODA file: {nucleus_path}")
        return None

    if hist_path != f"/HERMES_2007/zh/multiplicity_{species}":
        raise ValueError("R_A requires /HERMES_2007/zh histograms; regenerate the analyzer output")
    return optional_data(load_ratio, nucleus_path, deuterium, "zh", species)


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Plot HERMES hadron multiplicity nuclear modification factors "
            "R_A(z_h) for cross-section profile comparisons."
        )
    )
    ap.add_argument(
        "--config",
        default=os.path.join(SCRIPT_DIR, "RA_vs_zh_inputs.yaml"),
        help="YAML/JSON config listing the deuterium and nuclear YODA files.",
    )
    ap.add_argument(
        "--data-dir",
        default=os.path.abspath(
            os.path.join(
                SCRIPT_DIR, "..", "..", "..", "..", "experimental_data", "HERMES", "R_A"
            )
        ),
        help="Directory containing HERMES/R_A experimental CSVs.",
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
        default="RA_vs_zh.pdf",
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
    ap.add_argument("--no-exp", action="store_true", help="Disable HERMES data.")
    ap.add_argument("--xlim", nargs=2, type=float, default=(0.05, 1.35))
    ap.add_argument("--ylim", nargs=2, type=float, default=(-0.2, 1.7))
    ap.add_argument(
        "--figsize",
        nargs=2,
        type=float,
        default=(7.2, 9.1),
        metavar=("WIDTH", "HEIGHT"),
        help="Figure size in inches. Default is tuned for a LaTeX page with caption room.",
    )
    ap.add_argument(
        "--frame-linewidth",
        type=float,
        default=0.3,
        help="Line width for subplot frames/spines.",
    )
    ap.add_argument("--title", default="", help="Optional suptitle")

    args = ap.parse_args()

    config_path = os.path.abspath(args.config)
    config_dir = os.path.dirname(config_path)
    config = load_yaml_config(config_path)

    nuclei = list(config.get("nuclei", ["He", "Ne", "Kr", "Xe"]))
    particles = list(
        config.get("particles", ["pip", "pi0", "pim", "kp", "km", "p", "pbar"])
    )
    hist_base = args.hist_base or str(
        config.get("histogram_base", "/HERMES_2007/zh/multiplicity")
    )
    hist_pattern = args.hist_pattern or str(
        config.get("histogram_pattern", "{base}_{species}")
    )
    scenarios = scenario_defs_from_config(config, config_dir)

    particle_labels = {
        "pip": r"$\boldsymbol{\pi^+}$",
        "pim": r"$\boldsymbol{\pi^-}$",
        "kp": r"$\boldsymbol{K^+}$",
        "km": r"$\boldsymbol{K^-}$",
        "p": r"$\boldsymbol{p}$",
        "pbar": r"$\boldsymbol{\bar{p}}$",
        "pi0": r"$\boldsymbol{\pi^0}$",
    }

    exp_index = {} if args.no_exp else build_experimental_index(args.data_dir, nuclei)

    fig = plt.figure(figsize=tuple(args.figsize))
    grid = fig.add_gridspec(
        len(particles),
        len(nuclei),
        wspace=0.0,
        hspace=0.0,
    )

    main_axes = {}
    for ip, particle in enumerate(particles):
        for inu, nucleus in enumerate(nuclei):
            main_ax = fig.add_subplot(grid[ip, inu])
            main_axes[(particle, nucleus)] = main_ax

    for ip, particle in enumerate(particles):
        for inu, nucleus in enumerate(nuclei):
            ax = main_axes[(particle, nucleus)]

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
                labelsize=8,
                width=args.frame_linewidth,
            )
            ax.tick_params(
                axis="both",
                which="minor",
                labelsize=7,
                width=args.frame_linewidth,
            )
            ax.tick_params(axis="x", which="both", top=True, bottom=True)
            if ip < len(particles) - 1:
                ax.tick_params(axis="x", labelbottom=False)
            else:
                ax.set_xlabel(r"${z_h}$", fontsize=14)
            if inu > 0:
                ax.tick_params(
                    axis="y", which="both", left=False, right=False, labelleft=False
                )
            if ip == 0:
                ax.set_title(nucleus, fontsize=14, fontweight="bold", pad=5)
            if inu == 0:
                ax.set_ylabel(r"${R^h_A}$", fontsize=14)
                ax.text(
                    0.075,
                    0.90,
                    particle_labels.get(particle, particle),
                    transform=ax.transAxes,
                    ha="left",
                    va="top",
                    fontsize=10,
                )

    plotted_scenarios = set()
    data_handle_added = False
    for particle in particles:
        hist_path = full_hist_path(hist_base, hist_pattern, particle, args.raw)
        for nucleus in nuclei:
            ax = main_axes[(particle, nucleus)]

            exp_points = None
            if not args.no_exp:
                exp_file = exp_index.get((nucleus, particle))
                if exp_file is None:
                    print(f"[warn] Missing HERMES R_A table for {nucleus} {particle}")
                else:
                    ex, spans, ey, estat, esys = load_ra_points(exp_file)
                    exp_points = (ex, spans, ey, estat, esys)

            for scenario in scenarios:
                sim = load_sim_ra(scenario, nucleus, particle, hist_path)
                if sim is None or not sim[0]:
                    continue
                sx, sy, se = sim
                plotted_scenarios.add(scenario["label"])
                if exp_points is not None:
                    ex, spans, *_ = exp_points
                    positions = {round((lo + hi) / 2, 8): x for x, (lo, hi) in zip(ex, spans)}
                    sx = [positions.get(round(x, 8), x) for x in sx]
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
                    linewidth=1.1,
                    zorder=3,
                )

            if exp_points is not None:
                ex, spans, ey, estat, esys = exp_points
                for y, sys, (xlow, xhigh) in zip(ey, esys, spans):
                    y_low = max(y - sys, args.ylim[0])
                    y_high = min(y + sys, args.ylim[1])
                    ax.add_patch(
                        Rectangle(
                            (xlow, y_low),
                            xhigh - xlow,
                            y_high - y_low,
                            facecolor="0.75",
                            edgecolor="black",
                            alpha=0.35,
                            linewidth=0.55,
                            zorder=8,
                        )
                    )
                ax.errorbar(
                    ex,
                    ey,
                    yerr=estat,
                    fmt="o",
                    linestyle="none",
                    color="black",
                    ecolor="black",
                    elinewidth=0.45,
                    capsize=1.2,
                    capthick=0.45,
                    zorder=10,
                    markersize=2.8,
                    markeredgewidth=0.45,
                    markerfacecolor="black",
                    markeredgecolor="black",
                )
                data_handle_added = True

    if not plotted_scenarios and not data_handle_added:
        warn_skip("No available data for R_A figure")
        plt.close(fig)
        return

    scenario_handles = [
        Line2D(
            [0],
            [0],
            color=scenario["color"],
            linestyle=scenario["linestyle"],
            linewidth=1.1,
            label=scenario["label"],
        )
        for scenario in scenarios if scenario["label"] in plotted_scenarios
    ]
    first_ax = main_axes.get(("pip", "He"), main_axes[(particles[0], nuclei[0])])
    second_ax = main_axes.get(("pip", "Ne"), first_ax)
    legend_order = {
        label: i for i, label in enumerate(
            ["Early formation", "Mean", "Late formation", "Profile A", "Profile B", "Profile C"]
        )
    }
    scenario_handles.sort(
        key=lambda handle: legend_order.get(handle.get_label(), len(legend_order))
    )
    split = sum(
        handle.get_label() in {"Early formation", "Mean", "Late formation"}
        for handle in scenario_handles
    )
    legend_groups = (
        [(first_ax, scenario_handles[:split]), (second_ax, scenario_handles[split:])]
        if second_ax is not first_ax
        else [(first_ax, scenario_handles)]
    )
    for ax, handles in legend_groups:
        if not handles:
            continue
        sim_legend = ax.legend(
            handles=handles,
            loc="lower left",
            bbox_to_anchor=(0.02, 0.02),
            frameon=False,
            fontsize=8,
            handlelength=3.0,
            borderaxespad=0.0,
        )
        if ax is second_ax and data_handle_added:
            ax.add_artist(sim_legend)
    if data_handle_added:
        second_ax.legend(
            handles=[DataLegendHandle(True)],
            loc="upper left",
            bbox_to_anchor=(0.02, 0.98),
            frameon=False,
            fontsize=8,
            labels=[r"HERMES"],
            borderaxespad=0.0,
            handler_map={DataLegendHandle: HandlerDataLegend()},
        )

    if args.title:
        fig.suptitle(args.title, fontsize=10)

    plt.tight_layout(rect=(0, 0, 1, 0.98 if args.title else 1))
    fig.subplots_adjust(wspace=0.00, hspace=0.00)
    os.makedirs(args.output_dir, exist_ok=True)
    output_stem = os.path.splitext(args.output_filename)[0]
    for ext in (".pdf", ".png"):
        output_path = os.path.join(args.output_dir, output_stem + ext)
        plt.savefig(output_path, dpi=200)
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
