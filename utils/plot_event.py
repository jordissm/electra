#!/usr/bin/env python3
"""
plot_electra_tracks.py

Plot ELECTRA / SMASH OSCAR2013 full_event_history in the x-y plane.

Behavior
--------
- Fixed axes: x and y
- Fixed plotting window: x,y in [-6, 6]
- Spectators are shown only as gray initial circles
- Interacting particles are colored by PDG ID
- Momentum arrows have fixed length 0.1
- Particle labels are drawn at all visible initial / interaction / final points
- Tracks are drawn only over the lifetime of each particle ID
- Incoming tracks are solid except for type-5 decays, which are dotted
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle


# ------------------------------------------------------------
# Data structures
# ------------------------------------------------------------


@dataclass(frozen=True)
class State:
    t: float
    x: float
    y: float
    z: float
    mass: float
    p0: float
    px: float
    py: float
    pz: float
    pdg: int
    pid: int
    charge: int


@dataclass(frozen=True)
class TaggedState:
    state: State
    role: str  # "initial", "interaction_in", "interaction_out", "final"
    interaction_type: Optional[int] = None


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------


def parse_particle_line(line: str) -> State:
    parts = line.split()
    if len(parts) != 12:
        raise ValueError(f"Expected 12 columns, got {len(parts)}: {line}")

    return State(
        t=float(parts[0]),
        x=float(parts[1]),
        y=float(parts[2]),
        z=float(parts[3]),
        mass=float(parts[4]),
        p0=float(parts[5]),
        px=float(parts[6]),
        py=float(parts[7]),
        pz=float(parts[8]),
        pdg=int(parts[9]),
        pid=int(parts[10]),
        charge=int(parts[11]),
    )


def parse_interaction_header(line: str) -> Tuple[int, int, Optional[int]]:
    parts = line.split()
    nin = int(parts[3])
    nout = int(parts[5])

    interaction_type = None
    if "type" in parts:
        idx = parts.index("type")
        if idx + 1 < len(parts):
            try:
                interaction_type = int(parts[idx + 1])
            except ValueError:
                interaction_type = None

    return nin, nout, interaction_type


def same_state(a: TaggedState, b: TaggedState, tol: float = 1e-12) -> bool:
    sa, sb = a.state, b.state
    return (
        abs(sa.t - sb.t) < tol
        and abs(sa.x - sb.x) < tol
        and abs(sa.y - sb.y) < tol
        and abs(sa.z - sb.z) < tol
        and abs(sa.px - sb.px) < tol
        and abs(sa.py - sb.py) < tol
        and abs(sa.pz - sb.pz) < tol
        and sa.pdg == sb.pdg
        and sa.pid == sb.pid
        and a.role == b.role
        and a.interaction_type == b.interaction_type
    )


def deduplicate_tagged_states(states: List[TaggedState]) -> List[TaggedState]:
    order = {"initial": 0, "interaction_out": 1, "interaction_in": 2, "final": 3}
    states = sorted(states, key=lambda ts: (ts.state.t, order.get(ts.role, 99)))

    out: List[TaggedState] = []
    for ts in states:
        if not out or not same_state(out[-1], ts):
            out.append(ts)
    return out


def parse_oscar_full_event_history(path: str):
    tagged_by_pid: Dict[int, List[TaggedState]] = defaultdict(list)
    initial_ids: Set[int] = set()
    interacting_ids: Set[int] = set()
    decay_ids: Set[int] = set()

    mode: Optional[str] = None
    current_nin = 0
    current_nout = 0
    current_type: Optional[int] = None
    interaction_idx = 0

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("#!OSCAR2013"):
                continue
            if line.startswith("# Units:") or line.startswith("# SMASH-"):
                continue

            if line.startswith("# event"):
                if " in " in line:
                    mode = "initial"
                elif " out " in line:
                    mode = "final"
                else:
                    mode = None
                current_nin = 0
                current_nout = 0
                current_type = None
                interaction_idx = 0
                continue

            if line.startswith("# interaction"):
                current_nin, current_nout, current_type = parse_interaction_header(line)
                mode = "interaction"
                interaction_idx = 0
                continue

            if line.startswith("#"):
                continue

            s = parse_particle_line(line)

            if mode == "initial":
                tagged_by_pid[s.pid].append(TaggedState(s, "initial", None))
                initial_ids.add(s.pid)

            elif mode == "final":
                tagged_by_pid[s.pid].append(TaggedState(s, "final", None))

            elif mode == "interaction":
                interacting_ids.add(s.pid)

                if interaction_idx < current_nin:
                    tagged_by_pid[s.pid].append(
                        TaggedState(s, "interaction_in", current_type)
                    )
                    if current_type == 5:
                        decay_ids.add(s.pid)
                else:
                    tagged_by_pid[s.pid].append(
                        TaggedState(s, "interaction_out", current_type)
                    )

                interaction_idx += 1
                if interaction_idx >= current_nin + current_nout:
                    mode = None
                    current_nin = 0
                    current_nout = 0
                    current_type = None
                    interaction_idx = 0

    for pid in list(tagged_by_pid.keys()):
        tagged_by_pid[pid] = deduplicate_tagged_states(tagged_by_pid[pid])

    return tagged_by_pid, initial_ids, interacting_ids, decay_ids


# ------------------------------------------------------------
# Plot helpers
# ------------------------------------------------------------


def build_pdg_colormap(unique_pdgs: List[int]):
    cmaps = [plt.cm.tab20, plt.cm.tab20b, plt.cm.tab20c]
    colors = []
    for cmap in cmaps:
        colors.extend([cmap(i) for i in range(cmap.N)])

    out = {}
    for i, pdg in enumerate(sorted(unique_pdgs)):
        out[pdg] = colors[i % len(colors)]
    return out


def point_visible(
    x: float, y: float, xmin: float, xmax: float, ymin: float, ymax: float
) -> bool:
    return xmin <= x <= xmax and ymin <= y <= ymax


def add_momentum_arrow(ax, s: State, arrow_length: float = 0.1, alpha: float = 0.95):
    pmag = math.hypot(s.px, s.py)
    if pmag <= 1e-15:
        return

    ux = s.px / pmag
    uy = s.py / pmag

    ax.annotate(
        "",
        xy=(s.x + arrow_length * ux, s.y + arrow_length * uy),
        xytext=(s.x, s.y),
        arrowprops=dict(
            arrowstyle="->",
            lw=0.9,
            alpha=alpha,
            shrinkA=0.0,
            shrinkB=0.0,
        ),
        zorder=5,
    )


def draw_segment(ax, a: State, b: State, color, linestyle, linewidth, alpha):
    ax.plot(
        [a.x, b.x],
        [a.y, b.y],
        linestyle=linestyle,
        color=color,
        linewidth=linewidth,
        alpha=alpha,
        zorder=3,
    )


# ------------------------------------------------------------
# Main plotting logic
# ------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input OSCAR2013 full_event_history file")
    parser.add_argument("-o", "--output", default="tracks.pdf")
    parser.add_argument("--spectator-radius", type=float, default=0.25)
    parser.add_argument("--linewidth", type=float, default=1.7)
    parser.add_argument("--marker-size", type=float, default=20.0)
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--label-fontsize", type=float, default=7.0)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--title", default=None)
    parser.add_argument("--legend", action="store_true")
    args = parser.parse_args()

    tagged_by_pid, initial_ids, interacting_ids, decay_ids = (
        parse_oscar_full_event_history(args.input)
    )
    spectator_ids = initial_ids - interacting_ids

    interacting_pdgs = sorted(
        {
            tagged_by_pid[pid][0].state.pdg
            for pid in interacting_ids
            if tagged_by_pid[pid]
        }
    )
    pdg_to_color = build_pdg_colormap(interacting_pdgs)

    xmin, xmax = -6.0, 6.0
    ymin, ymax = -6.0, 6.0

    fig, ax = plt.subplots(figsize=(9, 9))

    # Spectators
    for pid in sorted(spectator_ids):
        states = tagged_by_pid.get(pid, [])
        if not states:
            continue

        s0 = min(
            (ts.state for ts in states if ts.role == "initial"),
            key=lambda s: s.t,
            default=None,
        )
        if s0 is None:
            continue

        if point_visible(s0.x, s0.y, xmin, xmax, ymin, ymax):
            ax.add_patch(
                Circle(
                    (s0.x, s0.y),
                    radius=args.spectator_radius,
                    edgecolor="0.55",
                    facecolor="none",
                    linewidth=1.0,
                    linestyle="-",
                    zorder=1,
                )
            )
            ax.text(
                s0.x,
                s0.y,
                f"{pid}",
                fontsize=args.label_fontsize,
                ha="left",
                va="bottom",
                color="0.35",
                zorder=6,
            )

    # Interacting particles
    for pid in sorted(interacting_ids):
        tagged = tagged_by_pid.get(pid, [])
        if not tagged:
            continue

        tagged = sorted(tagged, key=lambda ts: (ts.state.t, ts.role))
        pdg = tagged[0].state.pdg
        color = pdg_to_color[pdg]

        # draw points + labels + arrows
        for ts in tagged:
            s = ts.state

            ax.scatter(
                [s.x],
                [s.y],
                s=args.marker_size,
                color=color,
                edgecolors="none",
                alpha=args.alpha,
                zorder=4,
            )

            if point_visible(s.x, s.y, xmin, xmax, ymin, ymax):
                add_momentum_arrow(ax, s, arrow_length=0.5, alpha=args.alpha)
                ax.text(
                    s.x,
                    s.y,
                    f"{pid}",
                    fontsize=args.label_fontsize,
                    ha="left",
                    va="bottom",
                    color=color,
                    zorder=6,
                )

        # draw lifetime segments for this ID only
        for a_ts, b_ts in zip(tagged[:-1], tagged[1:]):
            a = a_ts.state
            b = b_ts.state

            # default solid
            linestyle = "-"

            # if the segment ends at a type-5 incoming vertex, dotted
            if b_ts.role == "interaction_in" and b_ts.interaction_type == 5:
                linestyle = ":"

            draw_segment(
                ax,
                a,
                b,
                color=color,
                linestyle=linestyle,
                linewidth=args.linewidth,
                alpha=args.alpha,
            )

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xlabel("x [fm]")
    ax.set_ylabel("y [fm]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.20, linewidth=0.5)

    if args.title:
        ax.set_title(args.title)
    else:
        ax.set_title("ELECTRA / SMASH particle tracks (x-y projection)")

    spectator_handle = Line2D(
        [0],
        [0],
        marker="o",
        linestyle="None",
        markerfacecolor="none",
        markeredgecolor="0.55",
        markersize=8,
        label="Spectator (initial only)",
    )
    solid_handle = Line2D(
        [0],
        [0],
        color="black",
        lw=1.7,
        linestyle="-",
        label="Track",
    )
    decay_handle = Line2D(
        [0],
        [0],
        color="black",
        lw=1.7,
        linestyle=":",
        label="Segment ending in type-5 decay",
    )

    if args.legend:
        handles = [spectator_handle, solid_handle, decay_handle]
        for pdg in sorted(interacting_pdgs):
            handles.append(
                Line2D(
                    [0],
                    [0],
                    color=pdg_to_color[pdg],
                    lw=2,
                    marker="o",
                    markersize=5,
                    label=f"PDG {pdg}",
                )
            )
        ax.legend(handles=handles, loc="best", fontsize=8, frameon=True)
    else:
        ax.legend(
            handles=[spectator_handle, solid_handle, decay_handle],
            loc="best",
            frameon=True,
        )

    fig.tight_layout()
    fig.savefig(args.output, dpi=args.dpi)
    plt.close(fig)

    print(f"Saved plot to {args.output}")
    print(f"Initial particles      : {len(initial_ids)}")
    print(f"Interacting particles  : {len(interacting_ids)}")
    print(f"Spectator particles    : {len(spectator_ids)}")
    print(f"Decay parents (type 5) : {len(decay_ids)}")


if __name__ == "__main__":
    main()
