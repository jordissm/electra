#!/usr/bin/env python3
import argparse
import csv
import math
import os
import re
from typing import Dict, List, Tuple, Optional

import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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
            markersize=10,
            transform=trans,
        )
        return [box, err, cap_low, cap_high, marker]


def parse_yoda_histo1d_v2(path: str, hist_path: str) -> Dict[str, object]:
    """
    Parse one YODA_HISTO1D_V2 block and return:
      bins: list of (xlow, xhigh, sumw, sumw2, numEntries)
      scaledBy: float or None
    """
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

            if not in_table:
                continue

            if not line or line.startswith("#"):
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
    for xlow, xhigh, sumw, sumw2, sumwx, sumwx2, num_entries in bins:
        xc = 0.5 * (xlow + xhigh)
        y = sumw
        ye = math.sqrt(sumw2) if sumw2 >= 0 else 0.0
        xs.append(xc)
        ys.append(y)
        yerrs.append(ye)
    return xs, ys, yerrs


def tag_zh(zlo: float, zhi: float) -> str:
    # Turn (0.2,0.3) -> "zh0p2_0p3" (filesystem/name-friendly)
    def fmt(x: float) -> str:
        s = f"{x:g}"
        s = s.replace(".", "p")
        s = s.replace("-", "m")
        return s

    return f"zh{fmt(zlo)}_{fmt(zhi)}"


def suffix_from_hepdata_particle(particle: str) -> str:
    mapping = {
        "pi+": "pip",
        "pi-": "pim",
        "K+": "kp",
        "K-": "km",
    }
    return mapping[particle]


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
                if not match:
                    continue
                particle, zlo, zhi = match.groups()
                index[
                    (
                        suffix_from_hepdata_particle(particle),
                        tag_zh(float(zlo), float(zhi)),
                    )
                ] = path
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
            if first.startswith("PT "):
                in_data_table = in_deuteron_block
                continue
            if first.startswith("#"):
                continue
            if not in_data_table or len(row) < 7:
                continue

            x = float(row[1])
            y = float(row[2])
            stat = max(abs(float(row[3])), abs(float(row[4])))
            sys = max(abs(float(row[5])), abs(float(row[6])))
            xs.append(x)
            ys.append(y)
            stat_errs.append(stat)
            sys_errs.append(sys)

    if not xs:
        raise RuntimeError(f"No Deuteron HEPData points found in '{path}'")

    return xs, ys, stat_errs, sys_errs


def default_profile_id(yoda_path: str) -> str:
    base = os.path.basename(yoda_path)
    if base.endswith(".yoda"):
        base = base[:-5]
    m = re.search(r"(?:profile[_-]?)?(\d{3,})$", base)
    if m:
        return m.group(1)
    toks = re.split(r"[_-]+", base)
    if len(toks) >= 2 and toks[-1]:
        return toks[-1]
    return base


def profile_label(yoda_path: str) -> str:
    pid = default_profile_id(yoda_path)
    return f"eHIJING+SMASH profile {pid}"


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
            f"--pt-bin-edges must have exactly {n_points + 1} entries "
            f"for {n_points} HEPData points"
        )
    return list(zip(edges, edges[1:]))


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Plot dN/(dpT dz_h) vs pT in multiple zh bins from Rivet YODA "
            "on a 2x2 particle/antiparticle grid."
        )
    )
    ap.add_argument(
        "--ehijing-decays",
        nargs="+",
        required=True,
        help="Input .yoda file(s) for eHIJING w. dec..",
    )
    ap.add_argument(
        "--smash-decays-only",
        nargs="+",
        required=True,
        help="Input .yoda file(s) for eHIJING + SMASH (dec. only).",
    )
    ap.add_argument(
        "--smash-decays-collisions",
        nargs="+",
        required=True,
        help="Input .yoda file(s) for eHIJING + SMASH (dec. and coll.).",
    )

    ap.add_argument(
        "--hist-base",
        default="/ELECTRA_MC_2026_DNDPTDZ/dN_dptdz",
        help="Base histogram path inside YODA (default: /ELECTRA_MC_2026_DNDPTDZ/dN_dptdz).",
    )
    ap.add_argument(
        "--hist-pattern",
        default="{base}_{suf}_{zh}",
        help=(
            "Histogram naming pattern. Available fields: {base} {suf} {zh}. "
            "Default: {base}_{suf}_{zh}. Example produced: /.../dN_dptdz_pip_zh0p2_0p3"
        ),
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="Use RAW histogram path instead (i.e. /RAW/<hist>)",
    )

    # zh bins fixed to your request, but allow override if needed
    ap.add_argument(
        "--zh-bins",
        nargs="+",
        default=["0.2,0.3", "0.3,0.4", "0.4,0.6", "0.6,0.8"],
        help="Space-separated list like: 0.2,0.3 0.3,0.4 0.4,0.6 0.6,0.8",
    )
    ap.add_argument(
        "--pt-bin-edges",
        nargs="+",
        type=float,
        default=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.2],
        help=(
            "pT bin edges used as systematic-box widths for HEPData points. "
            "Default: 0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 1.2"
        ),
    )

    ap.add_argument(
        "--no-errorbars",
        action="store_true",
        help="Disable simulation uncertainty bands.",
    )
    ap.add_argument(
        "--no-exp", action="store_true", help="Disable plotting experimental data."
    )
    ap.add_argument(
        "--hepdata-dir",
        default=os.path.join(
            os.path.dirname(__file__),
            "experimental_data",
            "HERMES",
            "DNDPTDZ",
        ),
        help=(
            "Directory containing HEPData-ins1208547-v1-Table_*.csv files "
            "for HERMES dN/(dpT dz_h). The Deuteron block is used."
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
        default=SCRIPT_DIR,
        help="Directory for the output image. Defaults to the script directory.",
    )
    ap.add_argument(
        "--output-filename",
        default="dndptdz.pdf",
        help="Output image filename.",
    )

    ap.add_argument("--xlabel", default=r"$p_T\ \mathrm{[GeV]}$", help="X label")
    ap.add_argument(
        "--ylabel",
        default=r"$\displaystyle{\frac{1}{N_{\mathrm{ev}}}\frac{dN}{dp_T\,dz_h}}$",
        help="Y label (left panels)",
    )

    ap.add_argument(
        "--xlim", nargs=2, type=float, default=(0.01, 1.10), metavar=("XMIN", "XMAX")
    )
    ap.add_argument(
        "--ylim", nargs=2, type=float, default=(2e-4, 2e3), metavar=("YMIN", "YMAX")
    )
    ap.add_argument(
        "--ratio-ylim",
        nargs=2,
        type=float,
        default=(-0.25, 2.25),
        metavar=("YMIN", "YMAX"),
        help="Y-axis limits for the simulation/data ratio panels.",
    )

    ap.add_argument(
        "--legend-loc",
        default="lower left",
        help="Legend location inside panels (default: lower left).",
    )
    ap.add_argument("--title", default="", help="Optional suptitle")

    args = ap.parse_args()

    # Parse zh bins
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

    scenario_defs = [
        (
            args.ehijing_decays,
            "eHIJING w. decays",
            ":",
        ),
        (
            args.smash_decays_only,
            "eHIJING + SMASH (dec. only)",
            "-.",
        ),
        (
            args.smash_decays_collisions,
            "eHIJING + SMASH (dec. and coll.)",
            "-",
        ),
    ]

    panel_defs = [
        ("pip", r"$\boldsymbol{\pi^+}$", "+"),
        ("pim", r"$\boldsymbol{\pi^-}$", "-"),
        ("kp", r"$\boldsymbol{K^+}$", "+"),
        ("km", r"$\boldsymbol{K^-}$", "-"),
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
    data_handles = []

    for ipanel, (ax, ratio_ax, (suf, title, charge)) in enumerate(
        zip(main_axes, ratio_axes, panel_defs)
    ):
        ax.set_yscale("log")
        ax.set_xlim(*args.xlim)
        ax.set_ylim(*args.ylim)
        if ipanel == 0:
            ax.set_ylabel(args.ylabel, fontsize=24)
        ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.tick_params(axis="both", which="major", labelsize=20)
        ax.tick_params(axis="both", which="minor", labelsize=18)
        ax.tick_params(axis="x", which="both", top=True, bottom=True, labelbottom=False)
        if ipanel > 0:
            ax.tick_params(
                axis="y", which="both", left=False, right=False, labelleft=False
            )

        ratio_ax.set_xlim(*args.xlim)
        ratio_ax.set_ylim(*args.ratio_ylim)
        ratio_ax.axhline(1.0, color="0.35", linewidth=1.0, zorder=1)
        ratio_ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ratio_ax.xaxis.set_minor_locator(AutoMinorLocator(4))
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
                    ex, ey, estat, esys = load_hepdata_deuteron_points(exp_file)
                    ex_spans = bin_spans_from_edges(len(ex), args.pt_bin_edges)
                    ex_p, ey_p, estat_p, esys_p, ex_spans_p = [], [], [], [], []
                    for x, y, stat, sys, span in zip(ex, ey, estat, esys, ex_spans):
                        if y > 0 and math.isfinite(y):
                            ex_p.append(x)
                            ey_p.append(y * zh_scale)
                            estat_p.append(stat * zh_scale)
                            esys_p.append(sys * zh_scale)
                            ex_spans_p.append(span)
                    exp_points = (ex_p, ey_p, estat_p, esys_p, ex_spans_p)

            for paths, _scenario_label, linestyle in scenario_defs:
                for yp in paths:
                    d = parse_yoda_histo1d_v2(yp, hist_path)
                    xs, ys, yerrs = build_xy(d["bins"])
                    xs_p, ys_p, yerrs_p = positive_points(
                        xs, ys, yerrs, zh_scale / args.scale
                    )
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

        if ipanel == 0:
            data_handles.append(DataLegendHandle(True))

    main_axes[1].legend(
        handles=zh_handles,
        loc="lower left",
        bbox_to_anchor=(0.02, 0.02),
        frameon=False,
        fontsize=15,
        borderaxespad=0.0,
    )
    scenario_handles = [
        Line2D([0], [0], color="black", linestyle=linestyle, linewidth=2.2, label=label)
        for _paths, label, linestyle in scenario_defs
    ]
    sim_legend = main_axes[0].legend(
        handles=scenario_handles,
        loc="lower left",
        bbox_to_anchor=(0.02, 0.02),
        frameon=False,
        fontsize=15,
        borderaxespad=0.0,
    )
    if not args.no_exp:
        main_axes[0].add_artist(sim_legend)
        main_axes[0].legend(
            handles=data_handles,
            loc="lower left",
            bbox_to_anchor=(0.02, 0.185),
            frameon=False,
            fontsize=15,
            labels=[r"HERMES"],
            borderaxespad=0.0,
            handler_map={DataLegendHandle: HandlerDataLegend()},
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
