#!/usr/bin/env python3
import argparse
import csv
import math
import os
import re
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import AutoMinorLocator, LogLocator, NullFormatter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
sys.path.insert(0, str(Path(ANALYSIS_DIR) / "scripts"))
from plot_inputs import MissingDataError, available_file, optional_data, warn_skip

# Show only the early/late formation limits; color identifies the z_h bin.
PROFILE_STYLES = {
    "000000": ("Early formation", "--"),
    "000005": ("Late formation", "-"),
}


class DataLegendHandle:
    pass


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
            markerfacecolor="black",
            markeredgecolor="black",
            markersize=10,
            transform=trans,
        )
        return [box, err, cap_low, cap_high, marker]


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
                except ValueError:
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
        raise MissingDataError(f"Did not find bins for hist '{hist_path}' in '{path}'")
    return {"scaledBy": scaled_by, "bins": bins}


def build_xy(bins: List[Tuple[float, float, float, float, float, float, float]]):
    xs, ys, yerrs = [], [], []
    for xlow, xhigh, sumw, sumw2, _sumwx, _sumwx2, _nent in bins:
        xs.append(0.5 * (xlow + xhigh))
        ys.append(sumw)
        yerrs.append(math.sqrt(sumw2) if sumw2 >= 0 else 0.0)
    return xs, ys, yerrs


def tag_zh(zlo: float, zhi: float) -> str:
    def fmt(x: float) -> str:
        return f"{x:g}".replace(".", "p").replace("-", "m")

    return f"zh{fmt(zlo)}_{fmt(zhi)}"


def suffix_from_hepdata_particle(particle: str) -> str:
    return {"pi+": "pip", "pi-": "pim", "K+": "kp", "K-": "km"}[particle]


def build_hepdata_index(directory: str) -> Dict[Tuple[str, str], str]:
    index: Dict[Tuple[str, str], str] = {}
    pattern = re.compile(
        r"description:\s*(pi\+|pi-|K\+|K-).*Z in the range "
        r"([0-9]+(?:\.[0-9]+)?)-([0-9]+(?:\.[0-9]+)?)"
    )
    for name in os.listdir(directory):
        if not name.startswith("HEPData-ins1208547-v1-Table_") or not name.endswith(
            ".csv"
        ):
            continue
        path = os.path.join(directory, name)
        with open(path, "r") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    particle, zlo, zhi = match.groups()
                    key = (
                        suffix_from_hepdata_particle(particle),
                        tag_zh(float(zlo), float(zhi)),
                    )
                    index[key] = path
                    break
    return index


def check_hepdata_system_and_energy(
    hepdata_paths, expected_energy: float = 27.6
) -> None:
    for path in sorted(set(hepdata_paths)):
        energies: List[float] = []
        has_deuteron = False
        with open(path, "r", newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                first = row[0].strip()
                if first.startswith("#: E(P=1) [GeV]") and len(row) > 1:
                    try:
                        energies.append(float(row[1]))
                    except ValueError:
                        print(f"[warn] Could not parse beam energy in {path}")
                elif first.startswith("#: RE") and "DEUT" in ",".join(row):
                    has_deuteron = True

        if not has_deuteron:
            print(f"[warn] Expected Deuteron system for e+d, but none found in {path}")
        for energy in energies:
            if not math.isclose(energy, expected_energy, rel_tol=0.0, abs_tol=1e-12):
                print(
                    f"[warn] Expected E_lab = {expected_energy:g} GeV, "
                    f"but found {energy:g} GeV in {path}"
                )


def load_hepdata_deuteron_points(
    path: str,
) -> Tuple[List[float], List[float], List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    stat_errs: List[float] = []
    sys_errs: List[float] = []
    in_deuteron_block = False
    in_data_table = False

    with open(path, "r", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            first = row[0].strip()
            if first.startswith("#: RE"):
                in_deuteron_block = "DEUT" in ",".join(row)
                in_data_table = False
                continue
            if first.startswith("X "):
                in_data_table = in_deuteron_block
                continue
            if first.startswith("#"):
                continue
            if not in_data_table or len(row) < 7:
                continue

            xs.append(float(row[1]))
            ys.append(float(row[2]))
            stat_errs.append(max(abs(float(row[3])), abs(float(row[4]))))
            sys_errs.append(max(abs(float(row[5])), abs(float(row[6]))))

    if not xs:
        raise MissingDataError(f"No Deuteron HEPData points found in '{path}'")
    return xs, ys, stat_errs, sys_errs


def formation_time_value(yoda_path: str) -> str:
    base = os.path.splitext(os.path.basename(yoda_path))[0]
    match = re.search(r"tau[=_-](.+)$", base)
    if match:
        return match.group(1)
    return base


def formation_time_label(yoda_path: str) -> str:
    base = os.path.splitext(os.path.basename(yoda_path))[0]
    if base.startswith("profile_"):
        pid = base[len("profile_"):]
        return PROFILE_STYLES.get(pid, (f"Profile {pid}", "-"))[0]
    value = formation_time_value(yoda_path)
    value_no_units = re.sub(r"fm$", "", value, flags=re.IGNORECASE)
    if value_no_units.lower() in {"inf", "infty", "infinity"}:
        return "Late formation"
    try:
        if float(value_no_units) == 0.0:
            return "Early formation"
    except ValueError:
        pass
    if value.lower().endswith("fm"):
        return rf"$\tau_\mathrm{{form}}={value_no_units}\,\mathrm{{fm}}$"
    return rf"$\tau_\mathrm{{form}}={value}$"


def build_formation_time_scenario_defs(yoda_paths: List[str]):
    scenario_defs = []
    scenario_styles = dict(PROFILE_STYLES.values())
    for path in yoda_paths:
        label = formation_time_label(path)
        if label not in scenario_styles:
            continue
        if not available_file(path):
            continue
        linestyle = scenario_styles[label]
        scenario_defs.append(([path], label, linestyle))
    if not scenario_defs:
        warn_skip("No nonempty early/late formation YODA files to compare")
    return scenario_defs


def positive_points(xs, ys, yerrs, scale: float = 1.0):
    xs_p, ys_p, yerrs_p = [], [], []
    for x, y, ye in zip(xs, ys, yerrs):
        if y > 0 and math.isfinite(y):
            xs_p.append(x)
            ys_p.append(y * scale)
            yerrs_p.append(ye * scale)
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


def ratio_points_with_errors(
    sim_xs: List[float],
    sim_ys: List[float],
    sim_yerrs: List[float],
    data_xs: List[float],
    data_ys: List[float],
    data_stats: List[float],
    data_systematics: List[float],
) -> Tuple[List[float], List[float], List[float]]:
    ratio_xs, ratios, ratio_errs = [], [], []
    for x, data_y, data_stat, data_sys in zip(
        data_xs, data_ys, data_stats, data_systematics
    ):
        sim_y, sim_yerr = interpolate_y_and_error(sim_xs, sim_ys, sim_yerrs, x)
        if sim_y is None or sim_y <= 0 or data_y <= 0:
            continue

        data_err = math.sqrt(data_stat**2 + data_sys**2)
        ratio = sim_y / data_y
        ratio_err = ratio * math.sqrt(
            (sim_yerr / sim_y) ** 2 + (data_err / data_y) ** 2
        )
        ratio_xs.append(x)
        ratios.append(ratio)
        ratio_errs.append(ratio_err)
    return ratio_xs, ratios, ratio_errs


def bin_spans_from_edges(
    n_points: int, edges: List[float]
) -> List[Tuple[float, float]]:
    if len(edges) != n_points + 1:
        raise ValueError(
            f"--xb-bin-edges must have exactly {n_points + 1} entries "
            f"for {n_points} HEPData points"
        )
    return list(zip(edges, edges[1:]))


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Plot dN/(dx_B dz_h) vs x_B in multiple zh bins from Rivet YODA "
            "using the cross-section-profile-comparison style."
        )
    )
    ap.add_argument(
        "--profile-files",
        "--tau-files",
        dest="profile_files",
        nargs="*",
        default=[],
        help=(
            "Input profile_XXXXXX.yoda files; only profile_000000 (Early formation) "
            "and profile_000005 (Late formation) are plotted. "
            "Legacy tau=0.0fm.yoda and tau=inf.yoda filenames are also supported."
        ),
    )
    ap.add_argument(
        "--hist-base",
        default="/ELECTRA_MC_2026_DNDXBDZ/dN_dxbdz",
        help="Base histogram path inside YODA (default: /ELECTRA_MC_2026_DNDXBDZ/dN_dxbdz).",
    )
    ap.add_argument(
        "--hist-pattern",
        default="{base}_{suf}_{zh}",
        help=(
            "Histogram naming pattern. Available fields: {base} {suf} {zh}. "
            "Default: {base}_{suf}_{zh}. Example produced: /.../dN_dxbdz_pip_zh0p2_0p3"
        ),
    )
    ap.add_argument("--raw", action="store_true", help="Use /RAW/<hist> path.")
    ap.add_argument(
        "--zh-bins",
        nargs="+",
        default=["0.2,0.3", "0.3,0.4", "0.4,0.6", "0.6,0.8"],
        help="Space-separated list like: 0.2,0.3 0.3,0.4 0.4,0.6 0.6,0.8",
    )
    ap.add_argument(
        "--xb-bin-edges",
        nargs="+",
        type=float,
        default=[0.023, 0.04, 0.055, 0.075, 0.1, 0.14, 0.2, 0.3, 0.4, 0.6],
        help=(
            "x_B bin edges used as systematic-box widths for HEPData points. "
            "Default: 0.023 0.04 0.055 0.075 0.1 0.14 0.2 0.3 0.4 0.6"
        ),
    )
    ap.add_argument(
        "--no-errorbars",
        action="store_true",
        help="Disable simulation uncertainty bands.",
    )
    ap.add_argument("--no-exp", action="store_true", help="Disable HERMES data.")
    ap.add_argument(
        "--hepdata-dir",
        default=os.path.join(
            ANALYSIS_DIR, "experimental_data", "HERMES", "R_A", "d", "DNDXBDZ"
        ),
        help=(
            "Directory containing HEPData-ins1208547-v1-Table_*.csv files "
            "for HERMES dN/(dx_B dz_h). The Deuteron block is used."
        ),
    )
    ap.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Divide ONLY simulation y (and yerr) by this factor.",
    )
    ap.add_argument(
        "--zh-scales",
        nargs="+",
        type=float,
        default=None,
        help=(
            "Multiplicative scale for each zh bin, applied to simulation and "
            "experimental y values after --scale. Defaults to 1,10,100,..."
        ),
    )
    ap.add_argument(
        "--output-dir",
        default=os.path.join(
            ANALYSIS_DIR, "output", "plots", "HERMES", "cross_section_profile_comparison", "R_A"
        ),
        help=(
            "Directory for the output image (default: "
            "analysis/output/plots/HERMES/cross_section_profile_comparison/R_A)."
        ),
    )
    ap.add_argument(
        "--output-filename",
        default="dndxbdz.pdf",
        help="Output image filename.",
    )
    ap.add_argument("--xlabel", default=r"$x_B$", help="X label")
    ap.add_argument(
        "--ylabel",
        default=r"${\frac{1}{N_{\mathrm{ev}}}\frac{dN}{dx_B\,dz_h}}$",
        help="Y label (left panel)",
    )
    ap.add_argument(
        "--xlim", nargs=2, type=float, default=(0.02, 0.7), metavar=("XMIN", "XMAX")
    )
    ap.add_argument(
        "--ylim", nargs=2, type=float, default=(2e-3, 3e3), metavar=("YMIN", "YMAX")
    )
    ap.add_argument(
        "--ratio-ylim",
        nargs=2,
        type=float,
        default=(-0.25, 2.25),
        metavar=("YMIN", "YMAX"),
        help="Y-axis limits for the simulation/data ratio panels.",
    )
    ap.add_argument("--title", default="", help="Optional suptitle")

    args = ap.parse_args()

    zh_bins: List[Tuple[float, float]] = []
    for tok in args.zh_bins:
        a, b = tok.split(",")
        zh_bins.append((float(a), float(b)))

    if args.zh_scales is None:
        zh_scales = [10.0**i for i in range(len(zh_bins))]
    else:
        if len(args.zh_scales) != len(zh_bins):
            raise ValueError("--zh-scales must have the same length as --zh-bins")
        zh_scales = args.zh_scales

    hepdata_index = {} if args.no_exp else build_hepdata_index(args.hepdata_dir)
    if not args.no_exp:
        check_hepdata_system_and_energy(hepdata_index.values())

    scenario_defs = build_formation_time_scenario_defs(args.profile_files)
    has_experimental_data = False
    plotted_scenarios = set()
    panel_defs = [
        ("pip", r"$\boldsymbol{\pi^+}$"),
        ("pim", r"$\boldsymbol{\pi^-}$"),
        ("kp", r"$\boldsymbol{K^+}$"),
        ("km", r"$\boldsymbol{K^-}$"),
    ]
    zh_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    def full_hist_path(base: str, suf: str, zh_tag: str) -> str:
        hp = args.hist_pattern.format(base=base, suf=suf, zh=zh_tag)
        if args.raw and not hp.startswith("/RAW/"):
            hp = "/RAW" + hp
        return hp

    fig = plt.figure(figsize=(18, 8))
    grid = fig.add_gridspec(
        2,
        4,
        height_ratios=(3.0, 0.85),
        wspace=0.0,
        hspace=0.0,
    )
    main_axes = []
    ratio_axes = []
    for ipanel in range(len(panel_defs)):
        if ipanel == 0:
            ax = fig.add_subplot(grid[0, ipanel])
            ratio_ax = fig.add_subplot(grid[1, ipanel], sharex=ax)
        else:
            ax = fig.add_subplot(
                grid[0, ipanel], sharex=main_axes[0], sharey=main_axes[0]
            )
            ratio_ax = fig.add_subplot(
                grid[1, ipanel], sharex=main_axes[0], sharey=ratio_axes[0]
            )
        main_axes.append(ax)
        ratio_axes.append(ratio_ax)

    zh_handles = []
    data_handles = [DataLegendHandle()]

    for ipanel, (ax, ratio_ax, (suf, title)) in enumerate(
        zip(main_axes, ratio_axes, panel_defs)
    ):
        ax.set_yscale("log")
        ax.set_xscale("log")
        ax.set_xlim(*args.xlim)
        ax.set_ylim(*args.ylim)
        if ipanel == 0:
            ax.set_ylabel(args.ylabel, fontsize=32)
        ax.xaxis.set_major_locator(LogLocator(base=10.0))
        ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=range(2, 10)))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis="both", which="major", labelsize=20)
        ax.tick_params(axis="both", which="minor", labelsize=18)
        ax.tick_params(axis="x", which="both", top=True, bottom=True, labelbottom=False)
        if ipanel > 0:
            ax.tick_params(
                axis="y", which="both", left=False, right=False, labelleft=False
            )

        ratio_ax.set_xscale("log")
        ratio_ax.set_xlim(*args.xlim)
        ratio_ax.set_ylim(*args.ratio_ylim)
        ratio_ax.axhline(1.0, color="0.35", linewidth=1.0, zorder=1)
        ratio_ax.xaxis.set_major_locator(LogLocator(base=10.0))
        ratio_ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=range(2, 10)))
        ratio_ax.xaxis.set_minor_formatter(NullFormatter())
        ratio_ax.yaxis.set_minor_locator(AutoMinorLocator(4))
        ratio_ax.tick_params(axis="both", which="major", labelsize=16)
        ratio_ax.tick_params(axis="both", which="minor", labelsize=14)
        ratio_ax.tick_params(axis="x", which="both", top=True, bottom=True)
        if ipanel > 0:
            ratio_ax.tick_params(
                axis="y", which="both", left=False, right=False, labelleft=False
            )
        ratio_ax.set_xlabel(args.xlabel, fontsize=24)
        if ipanel == 0:
            ratio_ax.set_ylabel(r"$\mathrm{Sim}/\mathrm{Data}$", fontsize=18)

        ax.text(
            0.95,
            0.96,
            title,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=32,
            fontweight="bold",
        )
        if ipanel == 2:
            ax.text(
                0.04,
                0.03,
                r"$e+d$" "\n" r"$E_{\mathrm{lab}} = 27.6\ \mathrm{GeV}$",
                transform=ax.transAxes,
                ha="left",
                va="bottom",
                fontsize=18,
            )

        for iz, ((zlo, zhi), zh_scale) in enumerate(zip(zh_bins, zh_scales)):
            zh_tag = tag_zh(zlo, zhi)
            color = zh_colors[iz % len(zh_colors)]
            scale_label = "" if zh_scale == 1 else rf" $\times {zh_scale:g}$"
            zh_label = rf"${zlo:g}<z_h<{zhi:g}${scale_label}"
            hist_path = full_hist_path(args.hist_base, suf, zh_tag)

            exp_points = None
            if not args.no_exp:
                exp_file = hepdata_index.get((suf, zh_tag))
                if exp_file is None:
                    print(f"[warn] Missing HEPData table for {suf} {zh_tag}")
                else:
                    values = optional_data(load_hepdata_deuteron_points, exp_file)
                    if values is not None:
                        ex, ey, estat, esys = values
                        ex_spans = bin_spans_from_edges(len(ex), args.xb_bin_edges)
                        ex_p, ey_p, estat_p, esys_p, ex_spans_p = [], [], [], [], []
                        for x, y, stat, sys, span in zip(ex, ey, estat, esys, ex_spans):
                            if y > 0 and math.isfinite(y):
                                ex_p.append(x)
                                ey_p.append(y * zh_scale)
                                estat_p.append(stat * zh_scale)
                                esys_p.append(sys * zh_scale)
                                ex_spans_p.append(span)
                        exp_points = (ex_p, ey_p, estat_p, esys_p, ex_spans_p)
                        has_experimental_data = has_experimental_data or bool(ex_p)

            for paths, _scenario_label, linestyle in scenario_defs:
                for yp in paths:
                    d = optional_data(parse_yoda_histo1d_v2, yp, hist_path)
                    if d is None:
                        continue
                    xs, ys, yerrs = build_xy(d["bins"])
                    xs_p, ys_p, yerrs_p = positive_points(
                        xs, ys, yerrs, zh_scale / args.scale
                    )
                    if not xs_p:
                        continue
                    plotted_scenarios.add(_scenario_label)
                    if not args.no_errorbars:
                        y_low = [
                            max(y - ye, args.ylim[0] * 0.1)
                            for y, ye in zip(ys_p, yerrs_p)
                        ]
                        y_high = [y + ye for y, ye in zip(ys_p, yerrs_p)]
                        ax.fill_between(
                            xs_p,
                            y_low,
                            y_high,
                            color=color,
                            alpha=0.10,
                            linewidth=0,
                            zorder=2,
                        )
                    ax.plot(
                        xs_p,
                        ys_p,
                        color=color,
                        linestyle=linestyle,
                        linewidth=2.2,
                        zorder=3,
                    )

                    if exp_points is not None:
                        ex_p, ey_p, estat_p, esys_p, _ex_spans_p = exp_points
                        ratio_xs, ratios, ratio_errs = ratio_points_with_errors(
                            xs_p, ys_p, yerrs_p, ex_p, ey_p, estat_p, esys_p
                        )
                        if ratio_xs:
                            ratio_ax.errorbar(
                                ratio_xs,
                                ratios,
                                yerr=None if args.no_errorbars else ratio_errs,
                                fmt="o",
                                color=color,
                                ecolor=color,
                                linestyle=linestyle,
                                linewidth=1.4,
                                elinewidth=1.0,
                                capsize=2,
                                markersize=4,
                                markerfacecolor="none",
                                markeredgecolor=color,
                                zorder=3,
                            )

            if ipanel == 0:
                zh_handles.append(
                    Line2D([0], [0], color=color, linewidth=2.0, label=zh_label)
                )

            if exp_points is not None:
                ex_p, ey_p, estat_p, esys_p, ex_spans_p = exp_points
                for y, sys, (xlow, xhigh) in zip(ey_p, esys_p, ex_spans_p):
                    y_low = max(y - sys, args.ylim[0] * 0.1)
                    y_high = y + sys
                    ax.add_patch(
                        Rectangle(
                            (xlow, y_low),
                            xhigh - xlow,
                            y_high - y_low,
                            facecolor=color,
                            edgecolor=color,
                            alpha=0.18,
                            linewidth=1.0,
                            zorder=8,
                        )
                    )
                ax.errorbar(
                    ex_p,
                    ey_p,
                    yerr=estat_p,
                    fmt="o",
                    linestyle="none",
                    color=color,
                    ecolor=color,
                    capsize=2,
                    zorder=10,
                    markersize=6,
                    markerfacecolor=color,
                    markeredgecolor=color,
                )

    main_axes[1].legend(
        handles=zh_handles,
        loc="lower left",
        bbox_to_anchor=(0.02, 0.02),
        frameon=False,
        fontsize=15,
        handlelength=3.0,
        borderaxespad=0.0,
    )
    if not plotted_scenarios and not has_experimental_data:
        warn_skip("No available data for HERMES spectrum figure")
        plt.close(fig)
        return

    scenario_handles = [
        Line2D([0], [0], color="black", linestyle=linestyle, linewidth=2.2, label=label)
        for _paths, label, linestyle in scenario_defs if label in plotted_scenarios
    ]
    legend_handles = list(scenario_handles)
    legend_labels = [handle.get_label() for handle in scenario_handles]
    if has_experimental_data:
        legend_handles.extend(data_handles)
        legend_labels.append("HERMES")
    main_axes[0].legend(
        handles=legend_handles,
        labels=legend_labels,
        handler_map={DataLegendHandle: HandlerDataLegend()},
        loc="lower left",
        bbox_to_anchor=(0.02, 0.02),
        frameon=False,
        fontsize=15,
        handlelength=3.0,
        borderaxespad=0.0,
    )

    if args.title:
        fig.suptitle(args.title, fontsize=24)

    plt.tight_layout(rect=(0, 0, 1, 0.95 if args.title else 1))
    fig.subplots_adjust(wspace=0.00, hspace=0.00)
    os.makedirs(args.output_dir, exist_ok=True)
    output_stem = os.path.splitext(args.output_filename)[0]
    for ext in (".pdf", ".png"):
        output_path = os.path.join(args.output_dir, output_stem + ext)
        plt.savefig(output_path, dpi=200)
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
