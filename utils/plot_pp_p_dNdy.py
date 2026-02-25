#!/usr/bin/env python3
import sys
import os
import math
import argparse

import matplotlib.pyplot as plt


def parse_yoda_hist(filename, hist_path="/SMASH_2025_PROTON_DNDY/dN_dy_p"):
    """
    Parse a YODA ASCII file and extract the Histo1D with the given path.
    Returns arrays: bin_centers, dN_dy, dN_dy_err
    """
    in_block = False
    in_table = False

    xs = []
    ys = []
    yerrs = []

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()

            if line.startswith("BEGIN YODA_HISTO1D") and hist_path in line:
                in_block = True
                in_table = False
                continue

            if not in_block:
                continue

            if line.startswith("END YODA_HISTO1D"):
                break

            if line.startswith("# xlow"):
                in_table = True
                continue

            if not in_table or not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 7:
                continue

            xlow, xhigh, sumw, sumw2 = map(float, parts[:4])

            width = xhigh - xlow
            if width <= 0:
                continue

            xc = 0.5 * (xlow + xhigh)
            y = sumw / width
            yerr = math.sqrt(sumw2) / width if sumw2 > 0 else 0.0

            xs.append(xc)
            ys.append(y)
            yerrs.append(yerr)

    if not xs:
        raise RuntimeError(f"Histogram '{hist_path}' not found or empty in '{filename}'")

    return xs, ys, yerrs


def read_experimental_points(filename="pp_p_dNdy_experimental.dat"):
    """
    Read experimental data from a file with columns:
      y dndy

    Lines starting with '#' and blank lines are ignored.
    """
    ys = []
    dndys = []

    with open(filename, "r") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            try:
                y, dndy = map(float, parts[:2])
            except ValueError:
                continue

            ys.append(y)
            dndys.append(dndy)

    if not ys:
        raise RuntimeError(f"No valid experimental points found in '{filename}'")

    return ys, dndys


def main():
    parser = argparse.ArgumentParser(description="Plot proton dN/dy from YODA files")
    parser.add_argument("yoda_files", nargs="+", help="Input YODA file(s)")
    parser.add_argument("-o", "--output", default="pp_p_dndy.png", help="Output image")
    parser.add_argument(
        "--path",
        default="/SMASH_2025_PROTON_DNDY/dN_dy_p",
        help="YODA histogram path",
    )
    parser.add_argument("--show", action="store_true", help="Show interactive plot")
    parser.add_argument(
        "--exp",
        action="store_true",
        help="Overlay experimental data from pp_p_dNdy_experimental.dat",
    )
    args = parser.parse_args()

    fig, ax = plt.subplots()

    # --- Simulation curves as bands ---
    for yfile in args.yoda_files:
        try:
            xs, ys, yerrs = parse_yoda_hist(yfile, hist_path=args.path)
        except Exception as e:
            print(f"[WARN] Skipping '{yfile}': {e}", file=sys.stderr)
            continue

        label = os.path.splitext(os.path.basename(yfile))[0]

        # central curve
        (line,) = ax.plot(xs, ys, "-", label=label, zorder=2)

        # uncertainty band
        ylo = [y - dy for y, dy in zip(ys, yerrs)]
        yhi = [y + dy for y, dy in zip(ys, yerrs)]
        ax.fill_between(
            xs,
            ylo,
            yhi,
            color=line.get_color(),
            alpha=0.7,
            linewidth=0,
            zorder=1,
        )

    # --- Experimental data (markers) ---
    if args.exp:
        exp_file = "pp_p_dNdy_experimental.dat"
        if os.path.exists(exp_file):
            try:
                exp_y, exp_dndy = read_experimental_points(exp_file)
                ax.plot(
                    exp_y,
                    exp_dndy,
                    linestyle="none",
                    marker="o",
                    markersize=6,
                    color="black",
                    label="NA49 data [EPJ C (2010) 65]",
                    zorder=20,  # always on top
                )
            except Exception as e:
                print(f"[WARN] Could not plot experimental data: {e}", file=sys.stderr)
        else:
            print(f"[WARN] Experimental file '{exp_file}' not found.", file=sys.stderr)

    if not ax.has_data():
        print("No valid histograms found.", file=sys.stderr)
        sys.exit(1)

    ax.set_xlabel(r"$y$")
    ax.set_ylabel(r"$dN/dy$")
    ax.grid(False)

    # Legend without frame
    handles, labels = ax.get_legend_handles_labels()
    if len(labels) > 1:
        ax.legend(frameon=False)

    print(f"Saving plot to '{args.output}'")
    fig.savefig(args.output, bbox_inches="tight")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
