import argparse
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle


@dataclass(frozen=True)
class Particle:
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


def parse_particle_line(line: str) -> Particle:
    parts = line.split()
    if len(parts) != 12:
        raise ValueError(f"Expected 12 columns, got {len(parts)}: {line}")

    return Particle(
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
    # Example: # interaction in 2 out 1 rho    0.0000000 weight     33.41279 partial   24.8583243 type     2
    parts = line.split()
    nin = int(parts[3])
    nout = int(parts[5])

    # Extract type if present
    proc_type = None
    if "type" in parts:
        type_idx = parts.index("type")
        proc_type = int(parts[type_idx + 1])

    return nin, nout, proc_type


def parse_full_event_history(path: Path):

    particles = defaultdict(lambda: defaultdict(list))

    mode: Optional[str] = None
    current_nin = 0
    current_nout = 0
    current_type: Optional[int] = None
    interaction_idx = 0

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip headers
            if line.startswith("#!OSCAR2013") or line.startswith("# SMASH-"):
                continue

            # Skip units
            if line.startswith("# Units:"):
                continue

            # Read event header
            if line.startswith("# event"):
                if "in" in line:
                    mode = "initial"
                elif "out" in line:
                    mode = "final"
                else:
                    mode = None
                continue

            # Read interaction header
            if line.startswith("# interaction"):
                mode = "interaction"
                current_nin, current_nout, current_proc_type = parse_interaction_header(
                    line
                )
                interaction_idx = 0
                continue

            # Parse particle line
            s = parse_particle_line(line)
            particles[s.pid]["xs"].append(s.x)
            particles[s.pid]["ys"].append(s.y)
            particles[s.pid]["pxs"].append(s.px)
            particles[s.pid]["pys"].append(s.py)
            particles[s.pid]["pdg"] = [s.pdg]

            if mode == "interaction":
                if interaction_idx < current_nin:
                    particles[s.pid]["mode"].append("interaction_in")
                elif interaction_idx < current_nin + current_nout:
                    particles[s.pid]["mode"].append("interaction_out")
                else:
                    particles[s.pid]["mode"].append("interaction_unknown")
                interaction_idx += 1
            else:
                particles[s.pid]["mode"].append(mode)

    return particles


def main():
    parser = argparse.ArgumentParser(
        description="Plot tracks from a full event history file"
    )
    parser.add_argument(
        "input_path", type=Path, help="Path to the full event history file"
    )
    parser.add_argument(
        "-o",
        "--output-name",
        type=Path,
        default="tracks.pdf",
        help="Path to save the plot (default: show on screen)",
    )
    args = parser.parse_args()

    particles = parse_full_event_history(args.input_path)

    xmin, xmax = -6.0, 6.0
    ymin, ymax = -6.0, 6.0

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    for pid, data in particles.items():
        print(f"Particle {pid} (PDG {data['pdg'][0]}):")
        print(f"  x: {data['xs']}")
        print(f"  y: {data['ys']}")
        print(f"  px: {data['pxs']}")
        print(f"  py: {data['pys']}")
        print(f"  modes: {data['mode']}")

        # Draw particles as circles
        for x, y, px, py, mode in zip(
            data["xs"], data["ys"], data["pxs"], data["pys"], data["mode"]
        ):
            if mode == "initial" or mode == "final":
                color = "blue"
            elif mode == "interaction":
                color = "red"
            else:
                color = "black"

            ax.add_patch(Circle((x, y), 0.04, color=color, alpha=0.5))

        # Draw track segments
        for i in range(1, len(data["xs"])):
            print(
                f"  Segment {i-1} -> {i}: ({data['xs'][i-1]}, {data['ys'][i-1]}) -> ({data['xs'][i]}, {data['ys'][i]}) mode={data['mode'][i]}"
            )
            x0, y0 = data["xs"][i - 1], data["ys"][i - 1]
            x1, y1 = data["xs"][i], data["ys"][i]
            mode = data["mode"][i]

            if mode == "final":
                color = "blue"
            elif mode == "interaction":
                color = "red"
            else:
                color = "black"

            ax.add_line(Line2D([x0, x1], [y0, y1], color=color, alpha=0.5))

        # Add PID labels to all recorded positions
        labeled_positions = set()
        for x, y in zip(data["xs"], data["ys"]):
            # Skip repeated positions to avoid clutter
            if (x, y) in labeled_positions:
                continue
            labeled_positions.add((x, y))
            ax.text(x, y, f"{pid}", fontsize=4, alpha=0.7)

    fig.tight_layout()
    fig.savefig(args.output_name)
    plt.close(fig)


if __name__ == "__main__":
    main()
