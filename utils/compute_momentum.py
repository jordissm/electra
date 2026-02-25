#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
yoda_mean_pt.py — Parse YODA_HISTO1D_V2 and compute mean pT with statistical uncertainty.

Usage
-----
  # basic: match first histo containing 'dNdpT_pion'
  python yoda_mean_pt.py /path/to/file.yoda --match dNdpT_pion

  # exact path matching
  python yoda_mean_pt.py file.yoda --path /RAW/SMASH_2023_I2693474/dNdpT_pion

  # recompute from bins and exclude overflow/underflow
  python yoda_mean_pt.py file.yoda --path /RAW/... --from-bins --exclude-overflow --exclude-underflow

Notes
-----
- By default, the script reproduces the YODA header "Mean" by using the "Total" row:
    mean = (Total sumwx) / (Total sumw)
  and computes SEM (standard error of the mean) using the unbiased weighted-variance estimator:
    S1 = Σ w,  S2 = Σ w^2,  Sx = Σ w x,  Sx2 = Σ w x^2
    μ̂  = Sx / S1
    s_w^2 (unbiased) = [S1 / (S1^2 - S2)] * (Sx2 - Sx^2 / S1)
    N_eff = S1^2 / S2
    SEM = sqrt( s_w^2 / N_eff ) = sqrt( s_w^2 * S2 / S1^2 )
- If you pass --from-bins, the script rebuilds (S1,S2,Sx,Sx2) from the per-bin table,
  optionally excluding under/overflow. This will typically differ slightly from the header “Mean”.
"""

from __future__ import annotations
import argparse
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

Block = List[str]

@dataclass
class HistoTotals:
    sumw: float
    sumw2: float
    sumwx: float
    sumwx2: float

@dataclass
class BinRow:
    xlow: float
    xhigh: float
    sumw: float
    sumw2: float
    sumwx: float
    sumwx2: float

@dataclass
class Histo:
    begin_line: str
    path: str
    totals: Optional[HistoTotals]
    underflow: Optional[HistoTotals]
    overflow: Optional[HistoTotals]
    bins: List[BinRow]

YODA_BEGIN_RE = re.compile(r"^BEGIN\s+YODA_HISTO1D_V2\s+(.+)$")
PATH_RE       = re.compile(r"^Path:\s+(.+)$")
TOTAL_RE      = re.compile(r"^\s*Total\s+Total\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)")
UNDERFLOW_RE  = re.compile(r"^\s*Underflow\s+Underflow\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)")
OVERFLOW_RE   = re.compile(r"^\s*Overflow\s+Overflow\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)")
BIN_HEADER_RE = re.compile(r"^\s*#\s*xlow")
BIN_ROW_RE    = re.compile(r"^\s*([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)\s+([eE0-9\.\+\-]+)")

def parse_yoda_histo_blocks(text: str) -> List[Histo]:
    """Parse all Histo1D V2 blocks in a YODA file string."""
    lines = text.splitlines()
    blocks: List[Block] = []
    current: Optional[Block] = None
    for ln in lines:
        if YODA_BEGIN_RE.match(ln):
            if current:
                blocks.append(current)
            current = [ln]
        elif current is not None:
            current.append(ln)
    if current:
        blocks.append(current)

    histos: List[Histo] = []
    for block in blocks:
        begin_line = block[0]
        path = ""
        totals = underflow = overflow = None
        bins: List[BinRow] = []
        in_bins = False
        for ln in block:
            m = PATH_RE.match(ln)
            if m:
                path = m.group(1).strip()
                continue
            if TOTAL_RE.match(ln):
                a, b, c, d = map(float, TOTAL_RE.match(ln).groups())
                totals = HistoTotals(a, b, c, d)
                continue
            if UNDERFLOW_RE.match(ln):
                a, b, c, d = map(float, UNDERFLOW_RE.match(ln).groups())
                underflow = HistoTotals(a, b, c, d)
                continue
            if OVERFLOW_RE.match(ln):
                a, b, c, d = map(float, OVERFLOW_RE.match(ln).groups())
                overflow = HistoTotals(a, b, c, d)
                continue
            if BIN_HEADER_RE.match(ln):
                in_bins = True
                continue
            if in_bins:
                m = BIN_ROW_RE.match(ln)
                if m:
                    xlow, xhigh, sw, sw2, swx, swx2 = map(float, m.groups())
                    bins.append(BinRow(xlow, xhigh, sw, sw2, swx, swx2))
                # stop when next block begins
                if YODA_BEGIN_RE.match(ln):
                    in_bins = False

        if path:
            histos.append(Histo(begin_line, path, totals, underflow, overflow, bins))
    return histos

def combine_stats_from_bins(bins: List[BinRow]) -> HistoTotals:
    S1  = sum(b.sumw  for b in bins)
    S2  = sum(b.sumw2 for b in bins)
    Sx  = sum(b.sumwx for b in bins)
    Sx2 = sum(b.sumwx2 for b in bins)
    return HistoTotals(S1, S2, Sx, Sx2)

def subtract(a: HistoTotals, b: Optional[HistoTotals]) -> HistoTotals:
    if b is None:
        return a
    return HistoTotals(
        a.sumw  - b.sumw,
        a.sumw2 - b.sumw2,
        a.sumwx - b.sumwx,
        a.sumwx2- b.sumwx2
    )

def weighted_mean_and_sem(S1: float, S2: float, Sx: float, Sx2: float) -> Tuple[float, float, float]:
    """
    Return (mean, unbiased_weighted_variance, SEM).
    - μ̂  = Sx / S1
    - s_w^2 (unbiased) = [S1 / (S1^2 - S2)] * (Sx2 - Sx^2 / S1)
    - N_eff = S1^2 / S2,  SEM = sqrt(s_w^2 / N_eff)
    Handles the unit-weight special case (S2≈S1) gracefully.
    """
    if S1 <= 0:
        raise ValueError("sumw (S1) must be positive.")
    mu = Sx / S1
    # protect against floating roundoff when all weights equal
    denom = S1*S1 - S2
    # raw (not yet unbiased) numerator of variance
    var_num = Sx2 - (Sx*Sx)/S1
    if denom <= 0:
        # fall back to standard (biased) variance estimate and N_eff heuristic
        # (this happens if effectively only 1 entry or S2≈S1 with extreme rounding)
        neff = S1*S1 / max(S2, 1e-16)
        sw2_unbiased = var_num / max(neff - 1.0, 1.0)
    else:
        sw2_unbiased = (S1 / denom) * var_num
        neff = (S1*S1) / max(S2, 1e-16)
    sem = (sw2_unbiased / neff) ** 0.5
    return mu, sw2_unbiased, sem

def select_histo(histos: List[Histo], path: Optional[str], match: Optional[str]) -> Histo:
    if path:
        for h in histos:
            if h.path == path:
                return h
        raise SystemExit(f"No histogram found with exact path: {path}")
    if match:
        # choose the first that contains the substring
        for h in histos:
            if match in h.path:
                return h
        raise SystemExit(f"No histogram path contains substring: {match}")
    if histos:
        return histos[0]
    raise SystemExit("No Histo1D V2 blocks found.")

def main():
    ap = argparse.ArgumentParser(description="Compute mean and uncertainty from YODA_HISTO1D_V2.")
    ap.add_argument("yoda_file", type=str, help="Path to YODA file")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--path", type=str, help="Exact histogram path to use")
    g.add_argument("--match", type=str, help="Substring to match in histogram path")
    ap.add_argument("--from-bins", action="store_true",
                    help="Rebuild totals from per-bin rows instead of using 'Total'")
    ap.add_argument("--exclude-underflow", action="store_true",
                    help="Exclude underflow contributions when using totals")
    ap.add_argument("--exclude-overflow", action="store_true",
                    help="Exclude overflow contributions when using totals")
    args = ap.parse_args()

    with open(args.yoda_file, "r", encoding="utf-8") as f:
        text = f.read()

    histos = parse_yoda_histo_blocks(text)
    h = select_histo(histos, args.path, args.match)

    if args.from_bins:
        totals = combine_stats_from_bins(h.bins)
        # From bins we have already excluded UF/OF by construction
        uf = of = None
    else:
        if h.totals is None:
            raise SystemExit("No 'Total' line found; try --from-bins.")
        totals = h.totals
        uf = h.underflow if args.exclude_underflow else None
        of = h.overflow   if args.exclude_overflow else None

    # optionally remove UF/OF from totals
    stats = subtract(subtract(totals, uf), of)

    mu, s2_unb, sem = weighted_mean_and_sem(stats.sumw, stats.sumw2, stats.sumwx, stats.sumwx2)

    # Pretty print
    method = "Totals (matches YODA header)" if not args.from_bins else "From per-bin rows"
    print(f"Histogram path: {h.path}")
    print(f"Computation   : {method}"
          + (" [UF excluded]" if args.exclude_underflow else "")
          + (" [OF excluded]" if args.exclude_overflow else ""))
    print(f"Sums          : S1=sumw={stats.sumw:.6e}, S2=sumw2={stats.sumw2:.6e}, "
          f"Sx=sumwx={stats.sumwx:.6e}, Sx2=sumwx2={stats.sumwx2:.6e}")
    print(f"Mean pT       : {mu:.9f}")
    print(f"StdErr(Mean)  : {sem:.9f}")
    print(f"Weighted Var  : {s2_unb:.9f}")

if __name__ == "__main__":
    main()
