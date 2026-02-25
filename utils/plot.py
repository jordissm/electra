#!/usr/bin/env python3
"""
Plot histograms and curves from a YODA (text) file WITHOUT the yoda library.

Supported objects (V2 text format):
  - YODA_HISTO1D_V2     -> step/bar plot (default shows density: sumw / binwidth)
  - YODA_PROFILE1D_V2   -> points (y = sumwy / sumw) with naive errors
  - YODA_SCATTER1D_V2   -> points with optional y-errors
  - YODA_SCATTER2D_V2   -> points with x/y symmetric/asymmetric errors

Usage:
  python plot_yoda_no_dep.py /path/to/file.yoda --outdir ./plots --show
  python plot_yoda_no_dep.py /path/to/file.yoda --outdir ./plots --save

Notes:
  * For Histo1D we display the bin *density* (sumw / binwidth). Use --heights=sumw to plot raw per-bin sums.
  * Error formulas for Profile1D are approximate (suitable for quick-look plots).
"""

from __future__ import annotations
import argparse
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import matplotlib.pyplot as plt


@dataclass
class Histo1D:
    path: str
    title: str
    bins: List[Tuple[float, float, float]]  # (xlow, xhigh, sumw)
    scaled_by: Optional[float] = None

@dataclass
class Profile1D:
    path: str
    title: str
    bins: List[Tuple[float, float, float, float, float]]  # (xlow, xhigh, sumw, sumwy, sumwy2)
    scaled_by: Optional[float] = None

@dataclass
class Scatter1D:
    path: str
    title: str
    points: List[Tuple[float, Optional[float], Optional[float]]]  # (x, y, yerr)
    scaled_by: Optional[float] = None

@dataclass
class Scatter2D:
    path: str
    title: str
    points: List[Tuple[float, float, Optional[Tuple[float, float]], Optional[Tuple[float, float]]]]
    # (x, y, xerr(-,+), yerr(-,+)); any may be None
    scaled_by: Optional[float] = None


def _to_float(s: str) -> float:
    s = s.strip()
    # Handle YODA's ".nan" and "nan"
    if s.lower() in {".nan", "nan"}:
        return float("nan")
    return float(s)



def parse_yoda_text(path: Path) -> Dict[str, object]:
    """Parse a YODA (text) file into simple Python structures."""
    txt = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    i, n = 0, len(txt)
    objects: Dict[str, object] = {}

    while i < n:
        line = txt[i]
        if not line.startswith("BEGIN "):
            i += 1
            continue

        header = line.strip()  # e.g., "BEGIN YODA_HISTO1D_V2 /Path"
        parts = header.split(maxsplit=2)
        if len(parts) < 2:
            i += 1
            continue
        obj_type = parts[1]  # e.g., YODA_HISTO1D_V2

        # Gather block lines until matching END
        j = i + 1
        while j < n and not txt[j].startswith("END "):
            j += 1
        block = txt[i:j+1]  # inclusive
        i = j + 1  # advance

        # Extract common metadata
        def find_prefix(prefix: str) -> Optional[str]:
            for ln in block:
                if ln.startswith(prefix):
                    return ln[len(prefix):].strip()
            return None

        yoda_path = find_prefix("Path:") or ""
        title = find_prefix("Title:") or ""
        scaled_by_raw = find_prefix("ScaledBy:")
        scaled_by = _to_float(scaled_by_raw) if scaled_by_raw else None

        # Find the data table start (after the '---' delimiter)
        delim_idx = next((k for k, ln in enumerate(block) if ln.strip() == '---'), None)
        if delim_idx is None:
            continue  # no table

        data_lines = block[delim_idx+1 : -1]  # exclude END

        # Route by type
        if obj_type == "YODA_HISTO1D_V2":
            # Expect header line starting with "# xlow xhigh sumw ..."
            bins: List[Tuple[float, float, float]] = []
            for dl in data_lines:
                if not dl or dl.startswith("#"):
                    continue
                cols = dl.split()
                if len(cols) < 3:
                    continue
                # Skip summary lines like 'Total', 'Underflow', 'Overflow'
                try:
                    xlow, xhigh, sumw = _to_float(cols[0]), _to_float(cols[1]), _to_float(cols[2])
                except Exception:
                    continue
                bins.append((xlow, xhigh, sumw))
            if bins:
                objects[yoda_path] = Histo1D(yoda_path, title, bins, scaled_by)

        elif obj_type == "YODA_PROFILE1D_V2":
            # Columns: xlow xhigh sumw sumw2 sumwx sumwx2 sumwy sumwy2 numEntries
            bins: List[Tuple[float, float, float, float, float]] = []
            for dl in data_lines:
                if not dl or dl.startswith("#"):
                    continue
                cols = dl.split()
                if len(cols) < 9:
                    continue
                try:
                    xlow, xhigh = _to_float(cols[0]), _to_float(cols[1])
                    sumw, sumwy, sumwy2 = _to_float(cols[2]), _to_float(cols[6]), _to_float(cols[7])
                except Exception:
                    continue
                bins.append((xlow, xhigh, sumw, sumwy, sumwy2))
            if bins:
                objects[yoda_path] = Profile1D(yoda_path, title, bins, scaled_by)

        elif obj_type == "YODA_SCATTER2D_V2":
            # Header expected: "# xval xerr- xerr+ yval yerr- yerr+"
            pts: List[Tuple[float, float, Optional[Tuple[float, float]], Optional[Tuple[float, float]]]] = []
            for dl in data_lines:
                if not dl or dl.startswith("#") or dl.startswith("ErrorBreakdown"):
                    continue
                cols = dl.split()
                if len(cols) < 6:
                    continue
                try:
                    x = _to_float(cols[0])
                    xm, xp = _to_float(cols[1]), _to_float(cols[2])
                    y = _to_float(cols[3])
                    ym, yp = _to_float(cols[4]), _to_float(cols[5])
                except Exception:
                    continue
                xerr = None if (math.isnan(xm) and math.isnan(xp)) else (xm, xp)
                yerr = None if (math.isnan(ym) and math.isnan(yp)) else (ym, yp)
                pts.append((x, y, xerr, yerr))
            if pts:
                objects[yoda_path] = Scatter2D(yoda_path, title, pts, scaled_by)

        elif obj_type == "YODA_SCATTER1D_V2":
            # Header expected: "# xval yval yerr?"
            pts: List[Tuple[float, Optional[float], Optional[float]]] = []
            for dl in data_lines:
                if not dl or dl.startswith("#"):
                    continue
                cols = dl.split()
                if len(cols) >= 2:
                    try:
                        x, y = _to_float(cols[0]), _to_float(cols[1])
                        yerr = _to_float(cols[2]) if len(cols) >= 3 else None
                    except Exception:
                        continue
                    pts.append((x, y, yerr))
            if pts:
                objects[yoda_path] = Scatter1D(yoda_path, title, pts, scaled_by)

        # Other object types (COUNTER, etc.) are ignored for plotting
    return objects


def plot_histo1d(obj: Histo1D, outdir: Path, heights: str = "density", show: bool = False) -> Path:
    # Compute edges and heights
    edges = [b[0] for b in obj.bins] + [obj.bins[-1][1]]
    widths = [b[1] - b[0] for b in obj.bins]
    sumw = [b[2] for b in obj.bins]

    if heights == "sumw":
        hvals = sumw
        ylabel = "sumw (per bin)"
    elif heights == "density":
        # density = sumw / binwidth
        hvals = [ (w / bw if bw != 0 else float('nan')) for w, bw in zip(sumw, widths) ]
        ylabel = "density (sumw / bin width)"
    else:
        raise ValueError("--heights must be 'density' or 'sumw'")

    fig, ax = plt.subplots()
    # Step plot using left-aligned edges
    ax.step(edges[:-1], hvals, where='post')
    ax.set_xlabel(obj.title if obj.title else obj.path.split('/')[-1])
    ax.set_ylabel(ylabel)
    ax.set_title(obj.path)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    outpath = outdir / (sanitize_filename(obj.path) + ".png")
    fig.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return outpath


def plot_profile1d(obj: Profile1D, outdir: Path, show: bool = False) -> Path:
    xs, ys, yerrs = [], [], []
    for (xlow, xhigh, sumw, sumwy, sumwy2) in obj.bins:
        x = 0.5 * (xlow + xhigh)
        if sumw > 0.0:
            y = sumwy / sumw
            # Approximate RMS about the mean from sumwy2 and sumwy
            # Treat sumwy2 as sum(w*y^2); variance ≈ sumwy2/sumw - (sumwy/sumw)^2
            var = max((sumwy2 / sumw) - y * y, 0.0)
            # Standard error: RMS / sqrt(N_eff). As a crude proxy use sqrt(sumw).
            yerr = math.sqrt(var) / math.sqrt(max(sumw, 1.0))
        else:
            y, yerr = float("nan"), float("nan")
        xs.append(x); ys.append(y); yerrs.append(yerr)

    fig, ax = plt.subplots()
    ax.errorbar(xs, ys, yerr=yerrs, fmt='o', capsize=2)
    ax.set_xlabel(obj.title if obj.title else obj.path.split('/')[-1])
    ax.set_ylabel("profile ⟨y⟩")
    ax.set_title(obj.path)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    outpath = outdir / (sanitize_filename(obj.path) + ".png")
    fig.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return outpath


def plot_scatter2d(obj: Scatter2D, outdir: Path, show: bool = False) -> Path:
    xs, ys, xerrm, xerrp, yerrm, yerrp = [], [], [], [], [], []
    for (x, y, xerr, yerr) in obj.points:
        xs.append(x); ys.append(y)
        if xerr is None:
            xerrm.append(0.0); xerrp.append(0.0)
        else:
            xerrm.append(xerr[0]); xerrp.append(xerr[1])
        if yerr is None:
            yerrm.append(0.0); yerrp.append(0.0)
        else:
            yerrm.append(yerr[0]); yerrp.append(yerr[1])

    import numpy as np
    xs_arr = np.array(xs)
    ys_arr = np.array(ys)
    # Mask NaNs in y
    mask = ~np.isnan(ys_arr)
    xs_arr, ys_arr = xs_arr[mask], ys_arr[mask]
    xerr_arr = np.vstack([np.array(xerrm), np.array(xerrp)])[:, mask]
    yerr_arr = np.vstack([np.array(yerrm), np.array(yerrp)])[:, mask]

    fig, ax = plt.subplots()
    # Asymmetric errors: xerr and yerr are 2xN arrays
    ax.errorbar(xs_arr, ys_arr, xerr=xerr_arr, yerr=yerr_arr, fmt='o', capsize=2)
    ax.set_xlabel(obj.title if obj.title else obj.path.split('/')[-1])
    ax.set_ylabel("value")
    ax.set_title(obj.path)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    outpath = outdir / (sanitize_filename(obj.path) + ".png")
    fig.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return outpath


def plot_scatter1d(obj: Scatter1D, outdir: Path, show: bool = False) -> Path:
    xs, ys, yerrs = [], [], []
    for (x, y, yerr) in obj.points:
        xs.append(x); ys.append(y); yerrs.append(yerr if yerr is not None else 0.0)

    fig, ax = plt.subplots()
    ax.errorbar(xs, ys, yerr=yerrs, fmt='o', capsize=2)
    ax.set_xlabel(obj.title if obj.title else obj.path.split('/')[-1])
    ax.set_ylabel("value")
    ax.set_title(obj.path)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    outpath = outdir / (sanitize_filename(obj.path) + ".png")
    fig.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close(fig)
    return outpath


def sanitize_filename(s: str) -> str:
    # Replace slashes and spaces to make a safe filename
    return s.strip().replace('/', '__').replace(' ', '_')


def main():
    ap = argparse.ArgumentParser(description="Plot YODA (text) without yoda dependency.")
    ap.add_argument("yoda_file", type=Path, help="Path to YODA .yoda text file")
    ap.add_argument("--outdir", type=Path, default=Path("plots"), help="Directory to write PNGs")
    ap.add_argument("--show", action="store_true", help="Display plots interactively")
    ap.add_argument("--save", action="store_true", help="Save plots to --outdir (default on)")
    ap.add_argument("--heights", choices=["density", "sumw"], default="density",
                    help="For Histo1D: plot 'density' (=sumw/binwidth) or raw 'sumw' per bin")
    args = ap.parse_args()

    if not args.yoda_file.exists():
        print(f"ERROR: File not found: {args.yoda_file}", file=sys.stderr)
        sys.exit(1)

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    objects = parse_yoda_text(args.yoda_file)
    if not objects:
        print("No plottable YODA objects found.", file=sys.stderr)
        sys.exit(2)

    print(f"Found {len(objects)} plottable objects. Writing to {outdir}")

    n_ok, n_err = 0, 0
    for path_key, obj in objects.items():
        try:
            if isinstance(obj, Histo1D):
                out = plot_histo1d(obj, outdir, heights=args.heights, show=args.show and not args.save)
            elif isinstance(obj, Profile1D):
                out = plot_profile1d(obj, outdir, show=args.show and not args.save)
            elif isinstance(obj, Scatter2D):
                out = plot_scatter2d(obj, outdir, show=args.show and not args.save)
            elif isinstance(obj, Scatter1D):
                out = plot_scatter1d(obj, outdir, show=args.show and not args.save)
            else:
                # Skip unknown/unsupported types
                continue
            print(f"  ✓ {path_key}  ->  {out}")
            n_ok += 1
        except Exception as ex:
            print(f"  ✗ {path_key}: {ex}", file=sys.stderr)
            n_err += 1

    print(f"Done. {n_ok} plots written; {n_err} errors.", file=sys.stderr)


if __name__ == "__main__":
    main()
