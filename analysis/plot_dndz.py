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
    bins: List[Tuple[float, float, float, float, float]] = (
        []
    )  # xlow,xhigh,sumw,sumw2,numEntries

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

            # table header
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
            # parts[4], parts[5] are sumwx, sumwx2 (not needed here)
            num_entries = float(parts[6]) if len(parts) >= 7 else 0.0

            bins.append((xlow, xhigh, sumw, sumw2, num_entries))

    if not bins:
        raise RuntimeError(f"Did not find bins for hist '{hist_path}' in '{path}'")

    return {"scaledBy": scaled_by, "bins": bins}


def build_xy(bins: List[Tuple[float, float, float, float, float]]):
    xs, ys, yerrs, widths = [], [], [], []

    for xlow, xhigh, sumw, sumw2, _nent in bins:
        xc = 0.5 * (xlow + xhigh)
        w = xhigh - xlow
        widths.append(w)

        y = sumw
        ye = math.sqrt(sumw2)

        xs.append(xc)
        ys.append(y)
        yerrs.append(ye)

    return xs, ys, yerrs, widths


def default_profile_id(yoda_path: str) -> str:
    """
    Extract a profile id from filename. Example:
      profile_000123.yoda -> 000123
      myrun_ABC.yoda -> ABC
    Falls back to the basename (without extension) if nothing obvious.
    """
    base = os.path.basename(yoda_path)
    if base.endswith(".yoda"):
        base = base[:-5]

    # Try: profile_XXXXXX or *_XXXXXX where X are digits
    m = re.search(r"(?:profile[_-]?)?(\d{3,})$", base)
    if m:
        return m.group(1)

    # Try last token after underscore/dash
    toks = re.split(r"[_-]+", base)
    if len(toks) >= 2 and toks[-1]:
        return toks[-1]

    return base


def profile_label(yoda_path: str) -> str:
    pid = default_profile_id(yoda_path)
    return f"eHIJING+SMASH profile {pid}"


def load_experimental_points(path: str) -> Tuple[List[float], List[float], List[float]]:
    """
    Experimental file format:
      z(or x)   y   yerr
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
            x = float(parts[0])
            y = float(parts[1])
            ye = float(parts[2])
            xs.append(x)
            ys.append(y)
            yerrs.append(ye)

    if not xs:
        raise RuntimeError(f"No experimental points found in '{path}'")

    return xs, ys, yerrs


def main():
    ap = argparse.ArgumentParser(
        description="Plot dN/dz_h per particle species from Rivet YODA_HISTO1D_V2, with optional HERMES data"
    )
    ap.add_argument("yoda", nargs="+", help="Input .yoda files (one or many)")

    ap.add_argument(
        "--hist-base",
        default="/EHIJING_SMASH_2026_DNDZ/dN_dzh",
        help=(
            "Histogram base path inside YODA (default: /EHIJING_SMASH_2026_DNDZ/dN_dzh). "
            "Species suffixes will be appended: _pip,_pim,_kp,_km,_p,_pbar."
        ),
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="Use RAW histogram path instead (i.e. /RAW/<hist>)",
    )
    ap.add_argument(
        "--no-errorbars",
        action="store_true",
        help="Disable simulation error bars (still uses bin centers).",
    )
    ap.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Divide ONLY the simulation y (and yerr) by this factor (default: 1). Use 1 for no scaling.",
    )

    # Experimental inputs
    ap.add_argument(
        "--exp-pattern",
        default="experimental_{suf}.dat",
        help=(
            "Pattern for experimental data files (default: experimental_{suf}.dat). "
            "Use {suf} for pip/pim/kp/km/p/pbar. Example: hermes_{suf}.txt"
        ),
    )
    ap.add_argument(
        "--no-exp",
        action="store_true",
        help="Disable plotting experimental data even if files exist.",
    )

    ap.add_argument(
        "-o",
        "--out",
        default="dndz.png",
        help="Output image filename (png/pdf/etc)",
    )
    ap.add_argument("--title", default="", help="Figure title (optional)")
    ap.add_argument("--xlabel", default=r"$z_h$", help="X label")
    ap.add_argument("--ylabel", default="", help="Y label (auto if empty)")
    ap.add_argument(
        "--xlim", nargs=2, type=float, default=None, metavar=("XMIN", "XMAX")
    )
    ap.add_argument(
        "--ylim", nargs=2, type=float, default=(0.0005, 10), metavar=("YMIN", "YMAX")
    )
    ap.add_argument(
        "--legend-loc",
        default="best",
        help="Legend location inside each panel (default: best). Examples: upper right, lower left, etc.",
    )

    args = ap.parse_args()

    # Species definitions: (suffix, pretty label)
    species = [
        ("pip", r"$\pi^{+}$"),
        ("pim", r"$\pi^{-}$"),
        ("kp", r"$K^{+}$"),
        ("km", r"$K^{-}$"),
        # ("p", r"$p$"),
        # ("pbar", r"$\bar{p}$"),
    ]

    if not args.ylabel:
        args.ylabel = r"$dN/dz_h$"

    # 1 row, 6 columns
    fig, axes = plt.subplots(1, 4, figsize=(16, 5), sharey=True)

    # Log y for all
    for ax in axes:
        ax.set_yscale("log")

    # Build hist paths for each species, respecting --raw
    def full_hist_path(base: str, suf: str) -> str:
        hp = f"{base}_{suf}"
        if args.raw and not hp.startswith("/RAW/"):
            hp = "/RAW" + hp
        return hp

    for ax, (suf, pretty) in zip(axes, species):
        hist_path = full_hist_path(args.hist_base, suf)

        # --- simulation curves ---
        for yp in args.yoda:
            d = parse_yoda_histo1d_v2(yp, hist_path)
            xs, ys, yerrs, _widths = build_xy(d["bins"])

            # Avoid log(0): mask non-positive bins
            xs_plot, ys_plot, yerrs_plot = [], [], []
            for x, y, ye in zip(xs, ys, yerrs):
                if y > 0 and math.isfinite(y):
                    xs_plot.append(x)
                    ys_plot.append(y / args.scale)
                    yerrs_plot.append(ye / args.scale)

            label = profile_label(yp)
            if args.no_errorbars:
                ax.plot(
                    xs_plot,
                    ys_plot,
                    marker="o",
                    linestyle="-",
                    label=label,
                )
            else:
                ax.errorbar(
                    xs_plot,
                    ys_plot,
                    yerr=yerrs_plot,
                    marker="o",
                    linestyle="-",
                    capsize=2,
                    label=label,
                )

        # --- experimental points (HERMES) ---
        if not args.no_exp:
            exp_file = args.exp_pattern.format(suf=suf)
            if os.path.exists(exp_file):
                try:
                    ex, ey, eye = load_experimental_points(exp_file)
                    # ey = [v / args.scale for v in ey]
                    # eye = [v / args.scale for v in eye]

                    # mask non-positive y for log scale
                    ex_p, ey_p, eye_p = [], [], []
                    for x, y, ye in zip(ex, ey, eye):
                        if y > 0 and math.isfinite(y):
                            ex_p.append(x)
                            ey_p.append(y)
                            eye_p.append(ye)

                    ax.errorbar(
                        ex_p,
                        ey_p,
                        yerr=eye_p,
                        fmt="o",
                        linestyle="none",
                        color="black",
                        ecolor="black",
                        elinewidth=1.2,
                        capsize=2,
                        label="HERMES",
                        zorder=10,
                    )
                except Exception as e:
                    # Don't crash the whole figure for a missing/bad exp file for one species
                    print(
                        f"[warn] Could not plot experimental data for '{suf}' from '{exp_file}': {e}"
                    )
            else:
                print(f"[warn] Experimental file not found for '{suf}': {exp_file}")

        # ax.set_title(pretty)
        # ax.grid(True, alpha=0.3)
        # Put particle label inside the axes, lower-left corner
        ax.text(
            0.1,
            0.1,
            pretty,  # (x,y) in axes fraction
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=30,
        )

        ax.text(
            0.5,
            0.5,
            "PRELIMINARY",  # (x,y) in axes fraction
            transform=ax.transAxes,
            alpha=0.2,
            color="red",
            ha="center",
            va="center",
            fontsize=24,
        )

        if args.xlim:
            ax.set_xlim(args.xlim[0], args.xlim[1])
        if args.ylim:
            ax.set_ylim(args.ylim[0], args.ylim[1])

        # Legend inside each panel
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc=args.legend_loc, frameon=False, fontsize=9)

    # Shared labels
    axes[0].set_ylabel(args.ylabel)
    for ax in axes:
        ax.set_xlabel(args.xlabel)

    if args.title:
        fig.suptitle(args.title)

    plt.tight_layout(rect=(0, 0, 1, 0.92 if args.title else 1))
    plt.savefig(args.out, dpi=200)
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
