#!/usr/bin/env python3
import argparse
import math
import os
import re
from typing import Dict, List, Tuple, Optional

import matplotlib.pyplot as plt


def parse_yoda_histo1d_v2(path: str, hist_path: str) -> Dict[str, object]:
    """
    Parse one YODA_HISTO1D_V2 block and return:
      bins: list of (xlow, xhigh, sumw, sumw2, numEntries)
      scaledBy: float or None
    """
    in_block = False
    in_table = False
    scaled_by = None
    bins: List[Tuple[float, float, float, float, float]] = []

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
            num_entries = float(parts[6]) if len(parts) >= 7 else 0.0
            bins.append((xlow, xhigh, sumw, sumw2, num_entries))

    if not bins:
        raise RuntimeError(f"Did not find bins for hist '{hist_path}' in '{path}'")

    return {"scaledBy": scaled_by, "bins": bins}


def build_xy(bins: List[Tuple[float, float, float, float, float]]):
    xs, ys, yerrs = [], [], []
    for xlow, xhigh, sumw, sumw2, _nent in bins:
        xc = 0.5 * (xlow + xhigh)
        y = sumw
        ye = math.sqrt(sumw2) if sumw2 >= 0 else 0.0
        xs.append(xc)
        ys.append(y)
        yerrs.append(ye)
    return xs, ys, yerrs


def load_experimental_points(path: str) -> Tuple[List[float], List[float], List[float]]:
    """
    Experimental file format:
      x   y   yerr
    - whitespace-separated
    - ignore blank lines and lines starting with '#'
    """
    xs: List[float] = []
    ys: List[float] = []
    yerrs: List[float] = []

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
            yerrs.append(float(parts[2]))

    if not xs:
        raise RuntimeError(f"No experimental points found in '{path}'")

    return xs, ys, yerrs


def tag_zh(zlo: float, zhi: float) -> str:
    # Turn (0.2,0.3) -> "zh0p2_0p3" (filesystem/name-friendly)
    def fmt(x: float) -> str:
        s = f"{x:g}"
        s = s.replace(".", "p")
        s = s.replace("-", "m")
        return s

    return f"zh{fmt(zlo)}_{fmt(zhi)}"


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


def main():
    ap = argparse.ArgumentParser(
        description="Plot dN/(dpT dz_h) vs pT in multiple zh bins (HERMES-style 2x4 grid) from Rivet YODA."
    )
    ap.add_argument("yoda", nargs="+", help="Input .yoda files (one or many)")

    ap.add_argument(
        "--hist-base",
        default="/EHIJING_SMASH_DNDPtDZ/dN_dptdz",
        help="Base histogram path inside YODA (default: /EHIJING_SMASH_DNDPtDZ/dN_dptdz).",
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
        "--no-errorbars", action="store_true", help="Disable simulation error bars."
    )
    ap.add_argument(
        "--no-exp", action="store_true", help="Disable plotting experimental data."
    )
    ap.add_argument(
        "--exp-pattern",
        default="experimental_{suf}_{zh}.dat",
        help=(
            "Pattern for experimental data files. Fields: {suf} {zh}. "
            "Default: experimental_{suf}_{zh}.dat (e.g. experimental_pip_zh0p2_0p3.dat)"
        ),
    )

    ap.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Divide ONLY simulation y (and yerr) by this factor.",
    )
    ap.add_argument(
        "-o", "--out", default="dN_dptdz_h2x4.png", help="Output image filename"
    )

    ap.add_argument("--xlabel", default=r"$p_T\ \mathrm{[GeV]}$", help="X label")
    ap.add_argument(
        "--ylabel", default=r"$dN/(dp_T\,dz_h)$", help="Y label (left panels)"
    )

    ap.add_argument(
        "--xlim", nargs=2, type=float, default=(0.0, 1.05), metavar=("XMIN", "XMAX")
    )
    ap.add_argument(
        "--ylim-pi", nargs=2, type=float, default=(2e-2, 1e1), metavar=("YMIN", "YMAX")
    )
    ap.add_argument(
        "--ylim-k", nargs=2, type=float, default=(2e-3, 2e0), metavar=("YMIN", "YMAX")
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

    # Species in each row
    row_defs = [
        ("pi", [("pip", r"$\pi^+$"), ("pim", r"$\pi^-$")]),
        ("k", [("kp", r"$K^+$"), ("km", r"$K^-$")]),
    ]

    # Styling to match the example figure vibe
    style = {
        "pip": dict(
            color="tab:red", marker="D", linestyle="-", linewidth=2.0, markersize=6
        ),
        "pim": dict(
            color="tab:blue",
            marker="D",
            linestyle="--",
            linewidth=2.0,
            markersize=6,
            fillstyle="none",
        ),
        "kp": dict(
            color="tab:red", marker="D", linestyle="-", linewidth=2.0, markersize=6
        ),
        "km": dict(
            color="tab:blue",
            marker="D",
            linestyle="--",
            linewidth=2.0,
            markersize=6,
            fillstyle="none",
        ),
    }

    def full_hist_path(base: str, suf: str, zh_tag: str) -> str:
        hp = args.hist_pattern.format(base=base, suf=suf, zh=zh_tag)
        if args.raw and not hp.startswith("/RAW/"):
            hp = "/RAW" + hp
        return hp

    # 2 rows x 4 cols
    fig, axes = plt.subplots(2, len(zh_bins), figsize=(16, 6), sharex=True)
    if len(zh_bins) == 1:
        # matplotlib oddity: axes shape changes if ncols=1
        axes = [[axes[0]], [axes[1]]]

    # Log y everywhere
    for r in range(2):
        for c in range(len(zh_bins)):
            axes[r][c].set_yscale("log")

    # Plot
    for c, (zlo, zhi) in enumerate(zh_bins):
        zh_tag = tag_zh(zlo, zhi)
        panel_title = rf"${zlo:g} < z_h < {zhi:g}$"

        # ---- top row: pions ----
        ax = axes[0][c]
        ax.set_title(panel_title, fontsize=16)
        ax.set_xlim(*args.xlim)
        ax.set_ylim(*args.ylim_pi)

        for suf, pretty in row_defs[0][1]:
            hist_path = full_hist_path(args.hist_base, suf, zh_tag)

            # simulation (one curve per input yoda)
            for yp in args.yoda:
                d = parse_yoda_histo1d_v2(yp, hist_path)
                xs, ys, yerrs = build_xy(d["bins"])

                xs_p, ys_p, yerrs_p = [], [], []
                for x, y, ye in zip(xs, ys, yerrs):
                    if y > 0 and math.isfinite(y):
                        xs_p.append(x)
                        ys_p.append(y / args.scale)
                        yerrs_p.append(ye / args.scale)

                lab = None
                # Only label the species once per panel for clarity (like HERMES legend)
                if len(args.yoda) == 1:
                    lab = f"HERMES {pretty}" if args.no_exp else f"Sim {pretty}"

                st = style[suf]
                if args.no_errorbars:
                    ax.plot(xs_p, ys_p, label=lab, **st)
                else:
                    ax.errorbar(xs_p, ys_p, yerr=yerrs_p, capsize=2, label=lab, **st)

            # experimental points
            if not args.no_exp:
                exp_file = args.exp_pattern.format(suf=suf, zh=zh_tag)
                if os.path.exists(exp_file):
                    ex, ey, eye = load_experimental_points(exp_file)
                    ex_p, ey_p, eye_p = [], [], []
                    for x, y, ye in zip(ex, ey, eye):
                        if y > 0 and math.isfinite(y):
                            ex_p.append(x)
                            ey_p.append(y)
                            eye_p.append(ye)
                    st = style[suf]
                    ax.errorbar(
                        ex_p,
                        ey_p,
                        yerr=eye_p,
                        fmt=st.get("marker", "o"),
                        linestyle="none",
                        color=st.get("color", "black"),
                        ecolor=st.get("color", "black"),
                        capsize=2,
                        label=f"HERMES {pretty}",
                        zorder=10,
                        markersize=6,
                        markerfacecolor=(
                            "none" if st.get("fillstyle") == "none" else st.get("color")
                        ),
                    )
                else:
                    print(f"[warn] Missing exp file: {exp_file}")

        if c == 0:
            ax.set_ylabel(args.ylabel, fontsize=16)

        # Legend like the paper (only first panel per row)
        if c == 0:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc=args.legend_loc, frameon=False, fontsize=12)

        # ---- bottom row: kaons ----
        ax = axes[1][c]
        ax.set_title(panel_title, fontsize=16)
        ax.set_xlim(*args.xlim)
        ax.set_ylim(*args.ylim_k)

        for suf, pretty in row_defs[1][1]:
            hist_path = full_hist_path(args.hist_base, suf, zh_tag)

            for yp in args.yoda:
                d = parse_yoda_histo1d_v2(yp, hist_path)
                xs, ys, yerrs = build_xy(d["bins"])

                xs_p, ys_p, yerrs_p = [], [], []
                for x, y, ye in zip(xs, ys, yerrs):
                    if y > 0 and math.isfinite(y):
                        xs_p.append(x)
                        ys_p.append(y / args.scale)
                        yerrs_p.append(ye / args.scale)

                st = style[suf]
                if args.no_errorbars:
                    ax.plot(xs_p, ys_p, **st)
                else:
                    ax.errorbar(xs_p, ys_p, yerr=yerrs_p, capsize=2, **st)

            if not args.no_exp:
                exp_file = args.exp_pattern.format(suf=suf, zh=zh_tag)
                if os.path.exists(exp_file):
                    ex, ey, eye = load_experimental_points(exp_file)
                    ex_p, ey_p, eye_p = [], [], []
                    for x, y, ye in zip(ex, ey, eye):
                        if y > 0 and math.isfinite(y):
                            ex_p.append(x)
                            ey_p.append(y)
                            eye_p.append(ye)
                    st = style[suf]
                    ax.errorbar(
                        ex_p,
                        ey_p,
                        yerr=eye_p,
                        fmt=st.get("marker", "o"),
                        linestyle="none",
                        color=st.get("color", "black"),
                        ecolor=st.get("color", "black"),
                        capsize=2,
                        label=f"HERMES {pretty}",
                        zorder=10,
                        markersize=6,
                        markerfacecolor=(
                            "none" if st.get("fillstyle") == "none" else st.get("color")
                        ),
                    )
                else:
                    print(f"[warn] Missing exp file: {exp_file}")

        if c == 0:
            ax.set_ylabel(args.ylabel, fontsize=16)

        if c == 0:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc=args.legend_loc, frameon=False, fontsize=12)

        ax.set_xlabel(args.xlabel, fontsize=16)

    if args.title:
        fig.suptitle(args.title, fontsize=16)

    plt.tight_layout(rect=(0, 0, 1, 0.95 if args.title else 1))
    plt.savefig(args.out, dpi=200)
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
