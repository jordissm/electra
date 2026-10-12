#!/usr/bin/env python3
"""Plot an eHIJING event_XXXXXXXX.fragmentation trace as a multipage PDF.

Requires matplotlib. Coordinates are taken directly from the trace in fm and
fm/c. Lines connecting breakups to a saved vertex are geometric guides, not
reconstructed particle worldlines. No OSCAR freestreaming/smearing is applied.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import math
from pathlib import Path
import re


PREFIX = re.compile(r"^\[pass=(\d+) string=(-?\d+)\]\s+(.*)$")
FIELDS = re.compile(r'(\w+)=("[^"]*"|\([^)]*\)|\S+)')
ANCESTOR = re.compile(r"\(pass=(\d+),string=(-?\d+),branch=([^)]*)\)")
Vertex = tuple[float, float, float, float]  # t, x, y, z
Group = tuple[int, int]  # pass, string


@dataclass
class Hadron:
    index: int
    pdg: int
    name: str
    group: Group
    branch: str
    saved: Vertex
    first: Vertex | None = None
    second: Vertex | None = None
    origin: Vertex | None = None
    prod_time: float | None = None
    output_id: int | None = None
    final_saved: Vertex | None = None
    ancestry: str = ""


@dataclass
class Trace:
    event: int
    attempt: int
    mode: int
    vertices: bool
    hadrons: list[Hadron] = field(default_factory=list)
    strings: dict[Group, dict[str, str]] = field(default_factory=dict)
    partons: dict[Group, list[tuple[int, int, Vertex]]] = field(default_factory=dict)


def point(value: str | None) -> Vertex | None:
    if value is None:
        return None
    values = tuple(float(item.strip()) for item in value.strip("()").split(","))
    if len(values) != 4 or not all(math.isfinite(item) for item in values):
        raise ValueError(f"Invalid spacetime vertex: {value}")
    return values


def time(value: str | None) -> float | None:
    if value is None or value.startswith("unavailable"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Invalid time: {value}")
    return result


def read_trace(path: Path) -> Trace:
    records: list[tuple[str, Group, dict[str, str]]] = []
    current: dict[str, str] | None = None
    strings: dict[Group, dict[str, str]] = {}
    partons: dict[Group, list[tuple[int, int, Vertex]]] = {}
    string_group: Group | None = None
    event = attempt = mode = None
    vertices = False
    version = ended = success = False
    with path.open(encoding="utf-8") as source:
        for raw in source:
            line = raw.strip()
            if line == "# eHIJING fragmentation trace v2":
                version = True
            elif line.startswith("Event:"):
                match = re.fullmatch(r"Event:\s+(-?\d+)\s+Attempt:\s+(\d+)", line)
                if not match:
                    raise ValueError("Invalid event header")
                event, attempt = map(int, match.groups())
            elif line.startswith("Settings:"):
                settings = dict(FIELDS.findall(line))
                mode = int(settings["mode"])
                vertices = settings.get("vertices") == "true"
            elif line == "End of fragmentation trace.":
                ended = True
            match = PREFIX.match(line)
            if match:
                group = (int(match[1]), int(match[2]))
                body = match[3]
                values = dict(FIELDS.findall(body))
                current = None
                string_group = None
                if body.startswith("STRING "):
                    strings[group] = values
                    string_group = group
                elif body.startswith("HADRON "):
                    current = values
                    records.append(("hadron", group, current))
                elif body.startswith("FINAL_EVENT "):
                    success = values.get("success") == "true"
            elif line.startswith("parton ") and string_group is not None:
                values = dict(FIELDS.findall(line))
                vertex = point(values.get("absolute_vertex"))
                if vertex is not None:
                    partons.setdefault(string_group, []).append(
                        (int(values["index"]), int(values["pdg"]), vertex))
            elif line.startswith("PARTICLE "):
                current = dict(FIELDS.findall(line))
                records.append(("particle", (-1, -1), current))
            elif current is not None:
                # Ancestor entries contain nested pass/string/branch fields;
                # retain them separately from this particle's own fields.
                current.update(FIELDS.findall(line.split("ancestor_strings=", 1)[0]))
                if "ancestor_strings=" in line:
                    current["ancestry"] = line
    if not version or event is None or attempt is None or mode is None:
        raise ValueError("Expected an eHIJING fragmentation trace v2 with event/settings headers")
    if not ended or not success:
        raise ValueError("The trace is incomplete or does not describe a successful event")

    trace = Trace(event, attempt, mode, vertices, strings=strings, partons=partons)
    by_source: dict[tuple[Group, int], Hadron] = {}
    for kind, group, values in records:
        if kind != "hadron":
            continue
        saved = point(values.get("saved_vertex"))
        if saved is None:
            raise ValueError(f"Hadron {values.get('index')} has no saved vertex")
        hadron = Hadron(
            int(values["index"]), int(values["pdg"]),
            values.get("name", "").strip('"'), group, values["branch"], saved,
            first=point(values.get("absolute_breakup_first")),
            second=point(values.get("absolute_breakup_second")),
            origin=point(values.get("inherited_origin")),
            prod_time=time(values.get("stored_prod_time")),
        )
        trace.hadrons.append(hadron)
        by_source[(group, hadron.index)] = hadron

    for kind, _, values in records:
        if kind != "particle" or values.get("final") != "true" or values.get("hadron") != "true":
            continue
        if "output_ID" not in values:
            raise ValueError("A final hadron is missing its OSCAR output_ID")
        index = int(values["index"])
        ancestry = values.get("ancestry", "")
        group = (-1, -1)
        if "source_pass" in values:
            group = (int(values["source_pass"]), int(values["source_string"]))
        else:
            ancestors = ANCESTOR.findall(ancestry)
            if len(ancestors) == 1:
                group = (int(ancestors[0][0]), int(ancestors[0][1]))
        saved = point(values.get("saved_vertex"))
        if saved is None:
            raise ValueError(f"Final hadron {index} has no saved vertex")
        hadron = by_source.get((group, index))
        if hadron is None:
            hadron = Hadron(
                index, int(values["pdg"]), values.get("name", "").strip('"'),
                group, values.get("branch", "decay/copy or unassigned"), saved,
                first=point(values.get("stored_breakup_first")),
                second=point(values.get("stored_breakup_second")), ancestry=ancestry,
            )
            trace.hadrons.append(hadron)
        hadron.output_id = int(values["output_ID"])
        hadron.final_saved = saved
        hadron.prod_time = time(values.get("prod_time"))
    if not trace.hadrons:
        raise ValueError("No hadron vertices found in the trace")
    return trace


def group_name(group: Group) -> str:
    if group == (-1, -1):
        return "Unassigned / multiple ancestor strings"
    return f"Pass {group[0]}, string {group[1]}"


def draw_diagram(trace, hadrons, axis, labels, title, colors, plt, Line2D):
    fig, ax = plt.subplots(figsize=(11.7, 8.3))
    component = {"x": 1, "y": 2, "z": 3}[axis]
    for group in sorted({h.group for h in hadrons}):
        for index, pdg, vertex in trace.partons.get(group, []):
            ax.plot(vertex[component], vertex[0], "x", color=colors[group], markersize=7)
            if labels:
                ax.annotate(f"P{index} (PDG {pdg})", (vertex[component], vertex[0]),
                            xytext=(4, -10), textcoords="offset points",
                            fontsize=7, color=colors[group])
    seen_breakups = set()
    for hadron in hadrons:
        color = colors[hadron.group]
        alpha = 0.85 if hadron.output_id is not None else 0.35
        for breakup in (hadron.first, hadron.second):
            if breakup is None:
                continue
            key = (hadron.group, breakup)
            if key not in seen_breakups:
                ax.plot(breakup[component], breakup[0], "o", color=color,
                        markerfacecolor="none", markersize=5, alpha=alpha)
                seen_breakups.add(key)
            ax.plot([breakup[component], hadron.saved[component]],
                    [breakup[0], hadron.saved[0]], "--", color=color,
                    linewidth=0.8, alpha=alpha * 0.6)
        if hadron.first is not None and hadron.second is not None:
            earlier = min((hadron.first, hadron.second), key=lambda vertex: vertex[0])
            ax.plot(earlier[component], earlier[0], "d", color=color,
                    markersize=4, alpha=alpha)
        if hadron.origin is not None:
            ax.plot(hadron.origin[component], hadron.origin[0], "+", color=color,
                    markersize=7, alpha=alpha)
        ax.plot(hadron.saved[component], hadron.saved[0], "*", color=color,
                markersize=9, alpha=alpha)
        if hadron.final_saved is not None and hadron.final_saved != hadron.saved:
            ax.plot(hadron.final_saved[component], hadron.final_saved[0], "s",
                    color=color, markerfacecolor="none", markersize=7)
        if labels:
            label = f"H{hadron.index} ({hadron.name or hadron.pdg})"
            if hadron.output_id is not None:
                label += f" / ID {hadron.output_id}"
            ax.annotate(label, (hadron.saved[component], hadron.saved[0]),
                        xytext=(4, 4), textcoords="offset points", fontsize=7,
                        color=color, alpha=alpha)

    saved_label = "Formation vertex" if trace.mode == 2 else "Saved hadron vertex"
    handles = [
        Line2D([], [], color="black", marker="o", markerfacecolor="none",
               linestyle="none", label="Breakup vertex (absolute)"),
        Line2D([], [], color="black", marker="d", linestyle="none", label="Earlier breakup"),
        Line2D([], [], color="black", marker="*", linestyle="none", label=saved_label),
        Line2D([], [], color="black", marker="+", linestyle="none", label="Inherited origin"),
        Line2D([], [], color="black", marker="x", linestyle="none", label="Input parton vertex"),
        Line2D([], [], color="black", linestyle="--", label="Geometric connection"),
    ]
    if any(h.final_saved is not None and h.final_saved != h.saved for h in hadrons):
        handles.append(Line2D([], [], color="black", marker="s", markerfacecolor="none",
                              linestyle="none", label="Changed vertex in final record"))
    for group in sorted({h.group for h in hadrons}):
        handles.append(Line2D([], [], color=colors[group], linewidth=2, label=group_name(group)))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    ax.set_xlabel(f"{axis} [fm]")
    ax.set_ylabel("t [fm/c]")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.2)
    ax.margins(0.15)
    ax.set_title(title + f"\nEvent {trace.event}, attempt {trace.attempt}, mode {trace.mode}")
    notes = "H = PYTHIA index; ID = OSCAR output_ID. Faded points: not exported.\n"
    notes += "Connections are geometric guides, not particle worldlines. No OSCAR smearing/freestreaming."
    if not trace.vertices:
        notes += "\nVertex generation is OFF; saved coordinates may be default zeros."
    elif trace.mode != 2:
        notes += "\nThe saved vertex is not necessarily the late formation point in this mode."
    fig.text(0.08, 0.03, notes, fontsize=8)
    fig.subplots_adjust(left=0.08, right=0.70, bottom=0.16, top=0.88)
    return fig


def time_tables(trace, hadrons, plt):
    rows = []
    for hadron in sorted(hadrons, key=lambda h: (h.group, h.index)):
        final = hadron.final_saved or hadron.saved
        rows.append([
            f"{hadron.group[0]}/{hadron.group[1]}" if hadron.group != (-1, -1) else "unassigned",
            str(hadron.index), str(hadron.output_id) if hadron.output_id is not None else "—",
            f"{hadron.name or hadron.pdg} ({hadron.pdg})",
            f"{hadron.prod_time:.8g}" if hadron.prod_time is not None else "unavailable",
            f"{hadron.saved[0]:.8g}", f"{final[0]:.8g}",
        ])
    headers = ["Pass/string", "H", "OSCAR ID", "Particle (PDG)", "prod_time", "saved t", "final t"]
    for start in range(0, len(rows), 32):
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.set_axis_off()
        ax.set_title(f"Event {trace.event}: hadron times [fm/c] — {start + 1}–{min(start + 32, len(rows))}", pad=20)
        page_rows = rows[start:start + 32]
        table = ax.table(cellText=page_rows, colLabels=headers, cellLoc="center",
                         colWidths=[0.13, 0.06, 0.09, 0.27, 0.15, 0.15, 0.15],
                         bbox=[0, 1 - (len(page_rows) + 1) / 36, 1, (len(page_rows) + 1) / 36])
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("0.8")
            if row == 0:
                cell.set_facecolor("0.9")
        fig.text(0.08, 0.05,
                 "saved t is the fragmentation vertex time; final t includes any later changes.\n"
                 "In mode 2, saved t is the formation time. Unavailable is distinct from zero.\n"
                 "An empty OSCAR ID means the particle was not exported; spectators are not included.", fontsize=8)
        fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.90)
        yield fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="event_XXXXXXXX.fragmentation file")
    parser.add_argument("-o", "--output", type=Path, help="PDF path (default: input with .pdf extension)")
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z", help="Spatial projection (default: z)")
    parser.add_argument("--string", type=int, help="Restrict to a string index")
    parser.add_argument("--pass", dest="pass_number", type=int, help="Restrict to a hadronization pass")
    parser.add_argument("--no-labels", action="store_true", help="Omit particle labels on diagrams")
    parser.add_argument("--overview-only", action="store_true", help="Save just the overview diagram")
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".pdf")
    if output.suffix.lower() != ".pdf":
        parser.error("Output must have a .pdf extension")
    try:
        trace = read_trace(args.input)
        hadrons = [h for h in trace.hadrons
                   if (args.string is None or h.group[1] == args.string)
                   and (args.pass_number is None or h.group[0] == args.pass_number)]
        if not hadrons:
            raise ValueError("No hadrons match the selected string/pass")
        import matplotlib
        matplotlib.use("Agg")  # Works on cluster nodes without a display.
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.lines import Line2D

        groups = sorted({h.group for h in hadrons})
        colors = {group: plt.get_cmap("tab20")(index % 20) for index, group in enumerate(groups)}
        with PdfPages(output, metadata={"Title": f"eHIJING event {trace.event} fragmentation",
                                        "Subject": "Hadronization spacetime diagram"}) as pdf:
            fig = draw_diagram(trace, hadrons, args.axis, not args.no_labels,
                               "Hadronization spacetime overview", colors, plt, Line2D)
            pdf.savefig(fig)
            plt.close(fig)
            if not args.overview_only:
                if len(groups) > 1:
                    for group in groups:
                        subset = [h for h in hadrons if h.group == group]
                        info = trace.strings.get(group, {})
                        title = group_name(group)
                        if info:
                            title += f" — {info.get('branch', '')}, {info.get('topology', '')}, mass {float(info['mass_GeV']):.6g} GeV"
                        fig = draw_diagram(trace, subset, args.axis, not args.no_labels,
                                           title, colors, plt, Line2D)
                        pdf.savefig(fig)
                        plt.close(fig)
                for fig in time_tables(trace, hadrons, plt):
                    pdf.savefig(fig)
                    plt.close(fig)
    except ImportError:
        parser.error("matplotlib is required: python3 -m pip install matplotlib")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(f"Saved {output} ({len(hadrons)} hadrons, {len(groups)} string/pass groups)")


if __name__ == "__main__":
    main()
