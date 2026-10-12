#!/usr/bin/env python3
"""Plot an eHIJING event_XXXXXXXX.fragmentation trace as a multipage PDF.

Requires matplotlib. Version 3 also records the massless-reference parameter
plane for longitudinal Lund constituent worldlines. Those are plotted separately
from the saved vertices: transverse smearing/tunnelling and heavy-endpoint
corrections do not define classical constituent paths through saved_vertex.
Hadron worldlines use dx/dt = p/E. No OSCAR smearing is applied.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import math
from pathlib import Path
import re


PREFIX = re.compile(r"^\[pass=(\d+) string=(-?\d+)\]\s+(.*)$")
FIELDS = re.compile(r'(\w+)=("[^"]*"|\([^)]*\)|\S+)')
MOMENTUM = re.compile(r"p\(E,px,py,pz\)_GeV=(\([^)]*\))")
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
    momentum: Vertex | None = None  # E, px, py, pz
    final_momentum: Vertex | None = None
    final_first: Vertex | None = None
    final_second: Vertex | None = None
    break_indices: tuple[int, int] | None = None


@dataclass
class Trace:
    event: int
    attempt: int
    mode: int
    vertices: bool
    hadrons: list[Hadron] = field(default_factory=list)
    strings: dict[Group, dict[str, str]] = field(default_factory=dict)
    partons: dict[Group, list[tuple[int, int, Vertex]]] = field(default_factory=dict)
    primary: Vertex | None = None
    planes: dict[tuple[Group, str], Plane] = field(default_factory=dict)
    version: int = 2


def fields(line: str) -> dict[str, str]:
    result = dict(FIELDS.findall(line))
    match = MOMENTUM.search(line)
    if match:
        result["momentum"] = match[1]
    return result


def add(a: Vertex, b: Vertex) -> Vertex:
    return tuple(x + y for x, y in zip(a, b))


def scale(a: Vertex, factor: float) -> Vertex:
    return tuple(x * factor for x in a)


def boost(vector: Vertex, beta: tuple[float, float, float]) -> Vertex:
    """Lorentz transform into a frame moving with beta (c = 1)."""
    b2 = sum(b * b for b in beta)
    if b2 == 0:
        return vector
    if b2 >= 1:
        raise ValueError("A string rest frame requires a timelike string momentum")
    gamma = 1 / math.sqrt(1 - b2)
    dot = sum(b * p for b, p in zip(beta, vector[1:]))
    factor = (gamma - 1) * dot / b2 - gamma * vector[0]
    return (gamma * (vector[0] - dot),
            *(p + factor * b for p, b in zip(vector[1:], beta)))


@dataclass
class Plane:
    maximum: int
    kappa: float
    regions: dict[tuple[int, int], tuple[Vertex, Vertex, Vertex]] = field(default_factory=dict)
    breaks: dict[int, tuple[float, float]] = field(default_factory=dict)

    def location(self, u: float, v: float) -> Vertex:
        # u/v increase toward the future; each integer is a region boundary.
        # At boundaries either adjacent region gives the same point. Missing
        # regions and nonphysical final-two solutions are not interpolated.
        for (pos, neg), (offset, plus, minus) in self.regions.items():
            xp, xn = u - (self.maximum - pos), v - (self.maximum - neg)
            if -1e-9 <= xp <= 1 + 1e-9 and -1e-9 <= xn <= 1 + 1e-9:
                return add(offset, scale(add(scale(plus, xp), scale(minus, xn)), 1 / self.kappa))
        raise ValueError("Constituent path leaves the recorded string parameter plane")

    def path(self, start: tuple[float, float], end: tuple[float, float]) -> list[Vertex]:
        """Follow one null characteristic, splitting it at every region edge."""
        if end[0] < start[0] - 1e-9 or end[1] < start[1] - 1e-9:
            raise ValueError("Constituent path would run backward in parameter time")
        varying = 0 if abs(end[0] - start[0]) > 1e-9 else 1
        fixed = 1 - varying
        if abs(start[fixed] - end[fixed]) > 1e-9:
            raise ValueError("A constituent characteristic must hold one light-cone coordinate fixed")
        lo, hi = start[varying], end[varying]
        cuts = [lo] + [float(i) for i in range(math.floor(lo) + 1, math.ceil(hi))] + [hi]
        result = []
        for left, right in zip(cuts, cuts[1:]):
            middle = (left + right) / 2
            for (pos, neg), (offset, plus, minus) in self.regions.items():
                uv = [start[0], start[1]]
                uv[varying] = middle
                xp, xn = uv[0] - (self.maximum - pos), uv[1] - (self.maximum - neg)
                if not (-1e-9 <= xp <= 1 + 1e-9 and -1e-9 <= xn <= 1 + 1e-9):
                    continue
                segment = []
                for value in (left, right):
                    uv[varying] = value
                    xp, xn = uv[0] - (self.maximum - pos), uv[1] - (self.maximum - neg)
                    segment.append(add(offset, scale(add(scale(plus, xp), scale(minus, xn)), 1 / self.kappa)))
                delta = add(segment[1], scale(segment[0], -1))
                if delta[0] < -1e-8 or abs(delta[0] ** 2 - sum(x * x for x in delta[1:])) > 1e-7 * max(1, delta[0] ** 2):
                    raise ValueError("Recorded constituent segment is not future-directed and lightlike")
                if result and max(abs(a - b) for a, b in zip(result[-1], segment[0])) > 1e-7:
                    raise ValueError("Recorded string regions do not join continuously")
                result.extend(segment if not result else segment[1:])
                break
            else:
                raise ValueError("No recorded region covers this constituent segment")
        return result


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
    planes: dict[tuple[Group, str], Plane] = {}
    primary = None
    event = attempt = mode = None
    vertices = False
    version = ended = success = False
    with path.open(encoding="utf-8") as source:
        for raw in source:
            line = raw.strip()
            if line in ("# eHIJING fragmentation trace v2", "# eHIJING fragmentation trace v3"):
                version = int(line[-1])
            elif line.startswith("Event:"):
                match = re.fullmatch(r"Event:\s+(-?\d+)\s+Attempt:\s+(\d+)", line)
                if not match:
                    raise ValueError("Invalid event header")
                event, attempt = map(int, match.groups())
            elif line.startswith("Settings:"):
                settings = fields(line)
                mode = int(settings["mode"])
                vertices = settings.get("vertices") == "true"
            elif line == "End of fragmentation trace.":
                ended = True
            match = PREFIX.match(line)
            if match:
                group = (int(match[1]), int(match[2]))
                body = match[3]
                values = fields(body)
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
                elif body.startswith("GEOMETRY "):
                    planes[(group, values["leg"])] = Plane(
                        int(values["max_region"]), float(values["kappa_GeV_per_fm"]))
                elif body.startswith("REGION ") and values["available"] == "true":
                    planes[(group, values["leg"])].regions[
                        (int(values["i_pos"]), int(values["i_neg"]))] = (
                            point(values["offset_fm"]), point(values["plus_GeV"]),
                            point(values["minus_GeV"]))
                elif body.startswith("PARAMETER_BREAKUP "):
                    plane = planes[(group, values["leg"])]
                    pos, neg = int(values["i_pos"]), int(values["i_neg"])
                    if pos >= 0 and neg >= 0:
                        plane.breaks[int(values["index"])] = (
                            plane.maximum - pos + float(values["x_pos"]),
                            plane.maximum - neg + float(values["x_neg"]))
                elif "nuclear_origin" in values:
                    primary = point(values["nuclear_origin"])
            elif line.startswith("parton ") and string_group is not None:
                values = fields(line)
                vertex = point(values.get("absolute_vertex"))
                if vertex is not None:
                    partons.setdefault(string_group, []).append(
                        (int(values["index"]), int(values["pdg"]), vertex))
            elif line.startswith("PARTICLE "):
                current = fields(line)
                records.append(("particle", (-1, -1), current))
            elif current is not None:
                # Ancestor entries contain nested pass/string/branch fields;
                # retain them separately from this particle's own fields.
                current.update(fields(line.split("ancestor_strings=", 1)[0]))
                if "ancestor_strings=" in line:
                    current["ancestry"] = line
    if not version or event is None or attempt is None or mode is None:
        raise ValueError("Expected an eHIJING fragmentation trace v2 or v3 with event/settings headers")
    if not ended or not success:
        raise ValueError("The trace is incomplete or does not describe a successful event")

    trace = Trace(event, attempt, mode, vertices, strings=strings, partons=partons,
                  primary=primary, planes=planes, version=version)
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
            momentum=point(values.get("momentum")),
            break_indices=tuple(int(item.lstrip("B")) for item in values["breaks"].split(","))
                if "breaks" in values else None,
        )
        trace.hadrons.append(hadron)
        by_source[(group, hadron.index)] = hadron

    for kind, _, values in records:
        if kind == "particle" and "source_pass" in values:
            group = (int(values["source_pass"]), int(values["source_string"]))
            hadron = by_source.get((group, int(values["index"])))
            # v2 stored momentum only in the final record. Use it at a saved
            # vertex only when that vertex is unchanged after fragmentation.
            if hadron is not None and hadron.momentum is None and point(values.get("saved_vertex")) == hadron.saved:
                hadron.momentum = point(values.get("momentum"))
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
                momentum=point(values.get("momentum")),
            )
            trace.hadrons.append(hadron)
        hadron.output_id = int(values["output_ID"])
        hadron.final_saved = saved
        hadron.final_momentum = point(values.get("momentum"))
        hadron.final_first = point(values.get("stored_breakup_first"))
        hadron.final_second = point(values.get("stored_breakup_second"))
        hadron.prod_time = time(values.get("prod_time"))
    if not trace.hadrons:
        raise ValueError("No hadron vertices found in the trace")
    return trace


def group_name(group: Group) -> str:
    if group == (-1, -1):
        return "Unassigned / multiple ancestor strings"
    return f"Pass {group[0]}, string {group[1]}"


def reference_hadron(trace: Trace, hadron: Hadron):
    plane = trace.planes.get((hadron.group, hadron.branch))
    if plane is None or hadron.break_indices is None or hadron.origin is None:
        raise ValueError("No parameter-plane record for this hadron")
    ia, ib = hadron.break_indices
    if ia not in plane.breaks or ib not in plane.breaks:
        raise ValueError("Final-two breakup has no standard parameter-plane coordinates")
    a, b = plane.breaks[ia], plane.breaks[ib]
    if a[0] < b[0] - 1e-9 or a[1] > b[1] + 1e-9:
        raise ValueError("Breakup pair is not ordered across the parameter plane")
    meeting = (a[0], b[1])
    paths = [plane.path(a, meeting), plane.path(b, meeting)]
    first, second = plane.location(*a), plane.location(*b)
    formation = plane.location(*meeting)
    if any(max(abs(a - b) for a, b in zip(path[-1], formation)) > 1e-7 for path in paths):
        raise ValueError("The two recorded constituent paths do not meet continuously")
    # Include the original endpoints moving outward before their first turn.
    # Boundary points B0/Bn are turns, not newly created quark pairs.
    boundary = max(plane.breaks)
    for index, uv, start in ((ia, a, (float(plane.maximum), 0.)),
                             (ib, b, (0., float(plane.maximum)))):
        if index not in (0, boundary) or trace.strings.get(hadron.group, {}).get("topology") != "open":
            continue
        if max(abs(x) for x in plane.location(*start)) < 1e-7:
            paths.append(plane.path(start, uv))
    momentum = scale(add(scale(formation, 2), scale(add(first, second), -1)), plane.kappa)
    return (add(hadron.origin, first), add(hadron.origin, second),
            add(hadron.origin, formation), momentum,
            [[add(hadron.origin, vertex) for vertex in path] for path in paths])


def draw_diagram(trace, hadrons, axis, labels, title, colors, plt, Line2D,
                 frame="lab", duration=None, longitudinal=False):
    fig, ax = plt.subplots(figsize=(11.7, 8.3))
    component = {"x": 1, "y": 2, "z": 3}[axis]
    groups = sorted({h.group for h in hadrons})
    beta = (0., 0., 0.)
    origin = (0., 0., 0., 0.)
    if frame == "string-rest":
        if len(groups) != 1:
            raise ValueError("Select one string/pass with --string and --pass for a common string rest frame")
        total = point(trace.strings.get(groups[0], {}).get("momentum"))
        if total is None or total[0] <= 0:
            raise ValueError("The selected string has no valid total momentum")
        beta = tuple(p / total[0] for p in total[1:])
        origin = trace.primary or origin

    def position(vertex):
        return boost(add(vertex, scale(origin, -1)), beta)

    def line(vertices, color, linestyle="-", alpha=1.):
        transformed = [position(vertex) for vertex in vertices]
        ax.plot([v[component] for v in transformed], [v[0] for v in transformed],
                color=color, linestyle=linestyle, linewidth=1.1, alpha=alpha)

    data = []
    skipped = 0
    for hadron in hadrons:
        if longitudinal:
            try:
                first, second, formation, momentum, paths = reference_hadron(trace, hadron)
            except ValueError:
                skipped += 1
                continue
        else:
            first, second, formation, momentum, paths = (
                hadron.first, hadron.second, hadron.saved, hadron.momentum, [])
        data.append((hadron, first, second, formation, momentum, paths))
    if longitudinal and not data:
        ax.set_axis_off()
        ax.set_title(title)
        ax.text(0.05, 0.65, "No reconstructable longitudinal constituent paths for this selection.\n"
                "Missing/invalid final-two parameter coordinates or discontinuous regions\n"
                "are not replaced by straight-line interpolation.\n"
                f"Omitted hadrons: {skipped}", transform=ax.transAxes)
        return fig
    times = [position(row[3])[0] for row in data]
    primary_time = position(trace.primary)[0] if trace.primary is not None else min(times)
    end_time = max(times) + (duration if duration is not None else max(1., 0.25 * (max(times) - primary_time)))
    seen_breakups = set()
    for hadron, first, second, formation, momentum, paths in data:
        color = colors[hadron.group]
        alpha = 1. if hadron.output_id is not None else 0.4
        for path in paths:
            line(path, color, alpha=alpha)
        for side, breakup in enumerate((first, second)):
            if breakup is None:
                continue
            key = (hadron.group, breakup)
            if key not in seen_breakups:
                vertex = position(breakup)
                ax.plot(vertex[component], vertex[0], "o", color="green",
                        markerfacecolor="green", markersize=6, alpha=alpha, zorder=5)
                if labels and hadron.break_indices is not None:
                    ax.annotate(f"B{hadron.break_indices[side]}",
                                (vertex[component], vertex[0]), xytext=(-5, -10),
                                textcoords="offset points", fontsize=7, color="green")
                seen_breakups.add(key)
        vertex = position(formation)
        ax.plot(vertex[component], vertex[0], "o", color="purple",
                markerfacecolor="purple", markersize=6, alpha=alpha, zorder=6)
        # Only exported final hadrons are extrapolated indefinitely; no invented
        # decay/interaction lifetime is assigned to nonfinal particles.
        if momentum is not None and hadron.output_id is not None:
            p = boost(momentum, beta)
            if p[0] > 0:
                end = (end_time, *(x + q / p[0] * (end_time - vertex[0])
                                   for x, q in zip(vertex[1:], p[1:])))
                ax.plot([vertex[component], end[component]], [vertex[0], end[0]],
                        color=color, linestyle="--", linewidth=1.1)
        if not longitudinal and hadron.final_saved is not None and hadron.final_saved != hadron.saved:
            final = position(hadron.final_saved)
            ax.plot(final[component], final[0], "s", color=color,
                    markerfacecolor="none", markersize=7)
        if labels:
            label = f"H{hadron.index} ({hadron.name or hadron.pdg})"
            if hadron.output_id is not None:
                label += f" / ID {hadron.output_id}"
            ax.annotate(label, (vertex[component], vertex[0]), xytext=(4, 4),
                        textcoords="offset points", fontsize=7, color=color, alpha=alpha)
    if trace.primary is not None:
        primary = position(trace.primary)
        ax.plot(primary[component], primary[0], "*", color="yellow", markerfacecolor="yellow",
                markeredgecolor="goldenrod", markersize=14, zorder=10)
        if labels:
            ax.annotate("primary", (primary[component], primary[0]), xytext=(8, -12),
                        textcoords="offset points", fontsize=7, color="goldenrod")
    saved_label = "Constituent meeting / formation" if longitudinal else (
        "Saved formation vertex" if trace.mode == 2 else "Saved hadron vertex")
    handles = [
        Line2D([], [], color="green", marker="o", linestyle="none", label="Breakup / boundary turn"),
        Line2D([], [], color="purple", marker="o", linestyle="none", label=saved_label),
        Line2D([], [], color="yellow", marker="*", markeredgecolor="goldenrod",
               markersize=12, linestyle="none", label="Primary vertex"),
        Line2D([], [], color="black", linestyle="--", label="Hadron worldline (p/E)"),
    ]
    if longitudinal:
        handles.append(Line2D([], [], color="black", linestyle="-", label="Longitudinal constituent worldline"))
    for group in groups:
        handles.append(Line2D([], [], color=colors[group], linewidth=2, label=group_name(group)))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    ax.set_xlabel(f"{axis} [fm]")
    ax.set_ylabel("t [fm/c]")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.2)
    ax.margins(0.15)
    ax.set_title(title + f"\nEvent {trace.event}, attempt {trace.attempt}, mode {trace.mode}; frame: {frame}")
    notes = "H = PYTHIA index; ID = OSCAR output_ID. Faded points: not exported.\n"
    if longitudinal:
        notes += "Classical longitudinal massless-reference Lund paths; transverse tunnelling/smearing and heavy-endpoint corrections excluded.\n"
        notes += "Formation points and hadron slopes on this page belong to the longitudinal reference picture."
        if skipped:
            notes += f"\n{skipped} hadron(s) omitted: missing/invalid parameter-plane path; no trajectory was interpolated."
    else:
        notes += "Recorded vertices; free hadron worldlines begin at saved formation points.\n"
        notes += "Smeared breakup-to-formation segments do not define causal constituent paths; see the longitudinal pages."
    if not trace.vertices:
        notes += "\nVertex generation is OFF; saved coordinates may be default zeros."
    elif trace.mode != 2:
        notes += "\nThe saved vertex is not necessarily the late formation point in this mode."
    fig.text(0.06, 0.025, notes, fontsize=7)
    fig.subplots_adjust(left=0.08, right=0.70, bottom=0.18, top=0.88)
    return fig


def time_tables(trace, hadrons, plt, frame="lab"):
    beta = (0., 0., 0.)
    origin = (0., 0., 0., 0.)
    if frame == "string-rest":
        group = hadrons[0].group
        total = point(trace.strings[group]["momentum"])
        beta = tuple(p / total[0] for p in total[1:])
        origin = trace.primary or origin

    def transformed_time(vertex):
        return boost(add(vertex, scale(origin, -1)), beta)[0]

    rows = []
    for hadron in sorted(hadrons, key=lambda h: (h.group, h.index)):
        final = hadron.final_saved or hadron.saved
        production = hadron.prod_time
        if frame != "lab" and production is not None:
            first = hadron.final_first or hadron.first
            second = hadron.final_second or hadron.second
            # Earliest breakup is frame dependent; never transform a scalar
            # production time as though it were an invariant or a four-vector.
            production = min(transformed_time(first), transformed_time(second)) if first is not None and second is not None else None
        rows.append([
            f"{hadron.group[0]}/{hadron.group[1]}" if hadron.group != (-1, -1) else "unassigned",
            str(hadron.index), str(hadron.output_id) if hadron.output_id is not None else "—",
            f"{hadron.name or hadron.pdg} ({hadron.pdg})",
            f"{production:.8g}" if production is not None else "unavailable",
            f"{transformed_time(hadron.saved):.8g}", f"{transformed_time(final):.8g}",
        ])
    headers = ["Pass/string", "H", "OSCAR ID", "Particle (PDG)", "prod_time", "saved t", "final t"]
    for start in range(0, len(rows), 32):
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.set_axis_off()
        ax.set_title(f"Event {trace.event}: saved-particle times [fm/c], {frame} — {start + 1}–{min(start + 32, len(rows))}", pad=20)
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
                 "An empty OSCAR ID means the particle was not exported; spectators are not included.\n"
                 "These times describe saved particle metadata; the longitudinal reference pages can have different formation points.", fontsize=8)
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
    parser.add_argument("--frame", choices=["lab", "string-rest"], default="lab",
                        help="Plot frame; string-rest requires one selected string/pass")
    parser.add_argument("--duration", type=float,
                        help="Continue free hadron worldlines this many fm/c past the last formation time")
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".pdf")
    if output.suffix.lower() != ".pdf":
        parser.error("Output must have a .pdf extension")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("--duration must be a positive finite time in fm/c")
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
        if args.frame == "string-rest" and len(groups) != 1:
            raise ValueError("Use --string and --pass to select one string for --frame string-rest")
        colors = {group: plt.get_cmap("tab20")(index % 20) for index, group in enumerate(groups)}
        with PdfPages(output, metadata={"Title": f"eHIJING event {trace.event} fragmentation",
                                        "Subject": "Hadronization spacetime diagram"}) as pdf:
            fig = draw_diagram(trace, hadrons, args.axis, not args.no_labels,
                               "Saved vertices and hadron worldlines", colors, plt, Line2D,
                               args.frame, args.duration)
            pdf.savefig(fig)
            plt.close(fig)
            if not args.overview_only:
                for group in groups:
                    subset = [h for h in hadrons if h.group == group]
                    info = trace.strings.get(group, {})
                    title = group_name(group)
                    if info:
                        title += f" — {info.get('branch', '')}, {info.get('topology', '')}, mass {float(info['mass_GeV']):.6g} GeV"
                    if len(groups) > 1:
                        fig = draw_diagram(trace, subset, args.axis, not args.no_labels,
                                           title, colors, plt, Line2D, args.frame, args.duration)
                        pdf.savefig(fig)
                        plt.close(fig)
                    if any(key[0] == group for key in trace.planes):
                        fig = draw_diagram(trace, subset, args.axis, not args.no_labels,
                                           "Longitudinal Lund worldlines: " + title,
                                           colors, plt, Line2D, args.frame, args.duration,
                                           longitudinal=True)
                        pdf.savefig(fig)
                        plt.close(fig)
                for fig in time_tables(trace, hadrons, plt, args.frame):
                    pdf.savefig(fig)
                    plt.close(fig)
    except ImportError:
        parser.error("matplotlib is required: python3 -m pip install matplotlib")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(f"Saved {output} ({len(hadrons)} hadrons, {len(groups)} string/pass groups)")
    if not trace.planes:
        print("Constituent worldlines require new v3 traces; this file only supports hadron worldlines.")


if __name__ == "__main__":
    main()
