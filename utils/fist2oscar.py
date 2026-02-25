#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File: fist2oscar.py

Description: Generates OSCAR2013 format machine-readable files for SMASH
from Thermal-FIST event generator output.

Inputs:
  - Particle list file (events.dat) from Thermal-FIST (required)
  - Output filepath for the OSCAR2013 file (required)
  - Optional PDG table (defaults to PDG21Plus_SMASH_masses_ThFIST.dat)

Example:
  ./fist2oscar.py \
    -p PDG21+/events.dat \
    -o PDG21+/pdg21plus_oscar0 \
    --pdg-table PDG21Plus_SMASH_masses_ThFIST.dat
"""

from __future__ import annotations

import itertools
from pathlib import Path
import argparse

import numpy as np
import pandas as pd

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.traceback import install as rich_traceback

console = Console()
rich_traceback(show_locals=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Thermal-FIST particle lists to OSCAR2013 format."
    )
    parser.add_argument(
        "-e", "--event-file",
        type=Path,
        required=True,
        help="Path to Thermal-FIST event file (e.g., events.dat)."
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="Output file path for OSCAR2013 file (will create parent dirs if needed)."
    )
    parser.add_argument(
        "--pdg-table",
        type=Path,
        default=Path("PDG21Plus_1.0_particles.dat"),
        help="Path to PDG table with masses/charges (default: PDG21Plus_1.0_particles.dat)."
    )
    return parser.parse_args()


def read_pdg_table(pdg_path: Path) -> pd.DataFrame:
    columns = [
        "pdgid", "Name", "Stable?", "Mass(GeV)", "Degeneracy", "Statistics",
        "Baryon no.", "Electric charge", "Strangeness no.", "Charm no.",
        "Absolute strangeness", "Absolute 'charmness'", "Width(GeV)", "Threshold(GeV)"
    ]
    df = pd.read_table(pdg_path, sep=r"\s+", header=None, names=columns, skiprows=1)
    # Ensure pdgid and Electric charge are numeric
    df["pdgid"] = pd.to_numeric(df["pdgid"], errors="coerce").astype("Int64")
    df["Electric charge"] = pd.to_numeric(df["Electric charge"], errors="coerce")
    df["Mass(GeV)"] = pd.to_numeric(df["Mass(GeV)"], errors="coerce")

    return df


def read_events(particle_list_path: Path) -> tuple[list[pd.DataFrame], list[str], list[str]]:
    event_dfs: list[pd.DataFrame] = []
    event_indices: list[str] = []
    event_weights: list[str] = []

    with particle_list_path.open("r") as f:
        is_header = lambda x: x.strip().startswith("Event") or x.strip().startswith("Weight")
        # Group alternating [headers][data rows] blocks
        for k, v in itertools.groupby(itertools.islice(f, None), key=is_header):
            block = list(v)
            if not k:
                # Data block -> DataFrame; first row are column names
                df = pd.DataFrame(map(str.split, block))
                df = df.rename(columns=df.iloc[0].to_dict()).drop(df.index[0])
                df = df.dropna(axis=0, how="all")
                event_dfs.append(df)
            else:
                # Header block -> capture event index & weight
                # Expect exactly two lines: "Event <idx>" then "Weight <w>"
                if len(block) >= 2:
                    event_indices.append(block[0].strip().replace("Event", "").strip())
                    event_weights.append(block[1].strip().replace("Weight", "").strip())

    return event_dfs, event_indices, event_weights



def enrich_and_format_events(event_dfs: list[pd.DataFrame], pdg: pd.DataFrame, *, tol: float = 1e-4) -> list[pd.DataFrame]:
    """
    Enrich events with mass/charge/ID, format columns for output, and
    print to console any particles that deviate from the on-shell condition:
        Δ = E^2 - p^2 - m^2
    A particle is flagged when |Δ| > tol (default 1e-6 in GeV^2).
    """
    time_column = ["r0[fm/c]"]
    pos_columns = ["rx[fm]", "ry[fm]", "rz[fm]"]
    mom_columns = ["p0[GeV/c2]", "px[GeV/c]", "py[GeV/c]", "pz[GeV/c]"]

    pdg_idx = pdg.set_index("pdgid")

    processed: list[pd.DataFrame] = []
    for iev, df in enumerate(event_dfs):
        # Ensure numeric types where needed
        for col in time_column + pos_columns + mom_columns + ["pdgid"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Add mass and charge via PDG lookup (abs(pdgid) for mass/charge sign from id)
        abs_ids = df["pdgid"].abs().astype("Int64")

        # Find which IDs are missing from the PDG table
        missing_ids = sorted(set(abs_ids.unique()) - set(pdg_idx.index))
        if missing_ids:
            raise ValueError(
                f"The following PDG IDs were not found in the PDG table: {missing_ids}\n"
                f"Total missing: {len(missing_ids)}"
            )

        # If we get here, all IDs are present — safe to index
        masses = pdg_idx.loc[abs_ids, "Mass(GeV)"].to_numpy()
        charges_mag = pdg_idx.loc[abs_ids, "Electric charge"].to_numpy()
        charges = np.sign(df["pdgid"].to_numpy()) * charges_mag

        df["mass[GeV]"] = masses
        df["charge"] = charges
        df["ID"] = np.arange(len(df), dtype=int)  # starts at 0

        # -------- On-shell check (does not modify saved dataframe) --------
        # Use numeric arrays before any formatting
        E  = df["p0[GeV/c2]"].to_numpy(dtype=float)
        px = df["px[GeV/c]"].to_numpy(dtype=float)
        py = df["py[GeV/c]"].to_numpy(dtype=float)
        pz = df["pz[GeV/c]"].to_numpy(dtype=float)
        m  = df["mass[GeV]"].to_numpy(dtype=float)

        p2 = px*px + py*py + pz*pz
        delta = np.sqrt(np.abs(E*E - p2 - m*m))  # GeV

        bad = np.where(delta > tol)[0]
        if bad.size:
            print(f"[event {iev}] {bad.size} particle(s) off-shell (|Δ| > {tol:g} GeV):")
            for i in bad:
                pid = int(df.iloc[i]["pdgid"])
                pid_abs = abs(pid)
                ident = int(df.iloc[i]["ID"])
                print(
                    f"  - ID={ident:6d}  PDG={pid:8d}  |Δ|={abs(delta[i]):.6e} GeV  "
                    f"(E={E[i]:.6e} GeV, |p|={np.sqrt(p2[i]):.6e} GeV, m={m[i]:.6e} GeV)"
                )
        # -------------------------------------------------------------------

        # Round/format columns (kept exactly as in your original code)
        df.loc[:, time_column] = df[time_column].apply(lambda x: x.astype(float).apply("{:.1f}".format))
        df.loc[:, pos_columns] = df[pos_columns].apply(lambda x: x.astype(float).apply("{:.5f}".format))
        df.loc[:, mom_columns] = df[mom_columns].apply(lambda x: x.astype(float).apply("{:.10f}".format))

        # Reorder
        df = df[time_column + pos_columns + ["mass[GeV]"] + mom_columns + ["pdgid", "ID", "charge"]]
        processed.append(df)

    return processed



def write_oscar(output_path: Path, event_dfs: list[pd.DataFrame], event_indices: list[str]) -> None:
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write header
    with output_path.open("w") as f:
        f.write("#!OSCAR2013 particle_lists t x y z mass p0 px py pz pdg ID charge \n")
        f.write("# Units: fm fm fm fm GeV GeV GeV GeV GeV none none e \n")

    # Append events
    for idx, df in enumerate(event_dfs):
        with output_path.open("a") as f:
            f.write(f"# event {event_indices[idx] if idx < len(event_indices) else (idx+1)} out {len(df)}\n")
        df.to_csv(output_path, sep=" ", index=False, header=False, mode="a")
        with output_path.open("a") as f:
            f.write(f"# event {event_indices[idx] if idx < len(event_indices) else (idx+1)} end 0 \n")


def main() -> None:
    args = parse_args()

    console.clear()
    info = Table(show_header=False, box=None)
    info.add_row("Event file:", f"[bold]{args.event_file}[/]")
    info.add_row("Output file:", f"[bold]{args.output}[/]")
    info.add_row("PDG table:", f"[bold]{args.pdg_table}[/]")
    console.print(Panel(info, title="[b]fist2oscar: Configuration[/b]", expand=False))

    # Validate inputs
    if not args.event_file.is_file():
        raise FileNotFoundError(f"Event file not found: {args.event_file}")
    if not args.pdg_table.is_file():
        raise FileNotFoundError(f"PDG table not found: {args.pdg_table}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        t_read = progress.add_task("Reading PDG table...", start=True)
        pdg = read_pdg_table(args.pdg_table)
        progress.update(t_read, description="Reading event file...")
        event_dfs, event_indices, event_weights = read_events(args.event_file)

        t_proc = progress.add_task("Processing events...", start=True)
        processed_dfs = enrich_and_format_events(event_dfs, pdg)

        t_write = progress.add_task("Writing OSCAR2013 output...", start=True)
        write_oscar(args.output, processed_dfs, event_indices)

    console.print(Panel.fit("[green]✅ OSCAR2013 ready to SMASH.[/green]"))


if __name__ == "__main__":
    main()
