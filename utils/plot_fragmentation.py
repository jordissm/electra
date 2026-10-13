#!/usr/bin/env python3
"""Plot an eHIJING event_XXXXXXXX.fragmentation trace as a multipage PDF.

Requires matplotlib. Reads v2/v3/v4 traces. Version 4 records converted
reference breakup points before heavy offsets and smearing. Reference paths
are validated against a continuous regional directrix and use inherited origins.
Unsupported classical paths/areas are omitted, not interpolated.
Lund reference boundaries are enabled on the overview and saved-vertex pages.
Hollow RB/RF markers distinguish reference breakups/meetings from stored
vertices. Dedicated Lund pages use each string's CM longitudinal axis.
Hadron worldlines use dx/dt = p/E. No OSCAR smearing is applied.
Single-hadron collapses show both the effective late Lund diamond and the
massive pre-collapse diagnostic by default. --collapse-model selects either.
Pages with the same frame/projection share axis limits; separate longitudinal
rest-frame pages share numerical scales, not a common physical rest frame.
Lab and individual-string rest-frame diagrams are included by default, followed
by particle-time tables. A multi-string overview has only a lab-frame view.
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
    production_first: Vertex | None = None
    production_second: Vertex | None = None
    final_production_first: Vertex | None = None
    final_production_second: Vertex | None = None
    production_basis: str = "legacy_breakup_pair"


@dataclass
class Parton:
    index: int
    pdg: int
    name: str
    role: str
    vertex: Vertex
    momentum: Vertex | None
    mass: float | None = None


@dataclass
class EndpointCurve:
    parton: Parton
    mass: float
    path: list[Vertex]
    turn: Vertex


@dataclass
class CollapseDiamond:
    hadron: Hadron
    origin: Vertex
    turns: tuple[Vertex, Vertex]
    paths: list[list[Vertex]]
    positive: Vertex


@dataclass
class Trace:
    event: int
    attempt: int
    mode: int
    vertices: bool
    hadrons: list[Hadron] = field(default_factory=list)
    strings: dict[Group, dict[str, str]] = field(default_factory=dict)
    partons: dict[Group, list[Parton]] = field(default_factory=dict)
    primary: Vertex | None = None
    planes: dict[tuple[Group, str], Plane] = field(default_factory=dict)
    version: int = 2
    kappa: float | None = None
    smear: bool | None = None


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


def dot(a: Vertex, b: Vertex) -> float:
    return a[0] * b[0] - sum(x * y for x, y in zip(a[1:], b[1:]))


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
    break_roles: dict[int, str] = field(default_factory=dict)
    raw_breaks: dict[int, tuple[int, int, float, float]] = field(default_factory=dict)
    effective: dict[int, Vertex] = field(default_factory=dict)
    invalid: dict[int, str] = field(default_factory=dict)
    origin: Vertex | None = None
    geometry_error: str = ""

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
        if max(abs(a - b) for a, b in zip(start, end)) < 1e-9:
            return [self.location(*start)]
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

    def string_cells(self) -> list[list[Vertex]]:
        """Surviving string area, excluding the future of every pair creation.

        A break removes its future quadrant in the Lund u/v plane. Subdivide
        recorded regions along break coordinates so each retained cell is
        entirely string, and map its corners with that region's own basis.
        Incomplete pair-creation coordinates cannot determine this area.
        """
        if self.geometry_error:
            raise ValueError(self.geometry_error)
        if self.invalid:
            raise ValueError("No worldsheet fill: some converted breakups leave the reference domain")
        ordered = sorted(self.break_roles)
        if any(i not in self.breaks for i in ordered):
            raise ValueError("No worldsheet fill: incomplete converted breakup coordinates")
        for ia, ib in zip(ordered, ordered[1:]):
            a, b = self.breaks[ia], self.breaks[ib]
            self.path(a, (a[0], b[1]))
            self.path(b, (a[0], b[1]))
        pair_indices = [i for i, role in self.break_roles.items() if role == "pair_creation"]
        if not self.break_roles or any(i not in self.breaks for i in pair_indices):
            raise ValueError("String area requires coordinates for every pair-creation breakup")
        breaks = [self.breaks[i] for i in pair_indices]
        cells = []
        for (pos, neg), (offset, plus, minus) in self.regions.items():
            u0, v0 = float(self.maximum - pos), float(self.maximum - neg)
            us = sorted({u0, u0 + 1, *(u for u, _ in breaks if u0 < u < u0 + 1)})
            vs = sorted({v0, v0 + 1, *(v for _, v in breaks if v0 < v < v0 + 1)})
            for left, right in zip(us, us[1:]):
                for bottom, top in zip(vs, vs[1:]):
                    middle = ((left + right) / 2, (bottom + top) / 2)
                    if any(middle[0] > u and middle[1] > v for u, v in breaks):
                        continue
                    cells.append([add(offset, scale(add(scale(plus, u - u0),
                        scale(minus, v - v0)), 1 / self.kappa))
                        for u, v in ((left, bottom), (right, bottom), (right, top), (left, top))])
        return cells


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
    partons: dict[Group, list[Parton]] = {}
    string_group: Group | None = None
    planes: dict[tuple[Group, str], Plane] = {}
    primary = None
    event = attempt = mode = None
    vertices = False
    kappa = None
    smear = None
    version = ended = success = False
    with path.open(encoding="utf-8") as source:
        for raw in source:
            line = raw.strip()
            if line in tuple(f"# eHIJING fragmentation trace v{i}" for i in (2, 3, 4)):
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
                kappa = time(settings.get("kappa_GeV_per_fm"))
                smear = {"true": True, "false": False}.get(settings.get("smear"))
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
                        int(values["max_region"]), float(values["kappa_GeV_per_fm"]),
                        origin=point(values.get("origin_fm")))
                elif body.startswith("REGION ") and values["available"] == "true":
                    planes[(group, values["leg"])].regions[
                        (int(values["i_pos"]), int(values["i_neg"]))] = (
                            point(values["offset_fm"]), point(values["plus_GeV"]),
                            point(values["minus_GeV"]))
                elif body.startswith("PARAMETER_BREAKUP "):
                    plane = planes[(group, values["leg"])]
                    plane.break_roles[int(values["index"])] = values["role"]
                    pos, neg = int(values["i_pos"]), int(values["i_neg"])
                    plane.raw_breaks[int(values["index"])] = (
                        pos, neg, float(values["x_pos"]), float(values["x_neg"]))
                elif body.startswith("REFERENCE_BREAKUP "):
                    planes[(group, values["leg"])].effective[int(values["index"])] = point(values["position_fm"])
                elif "nuclear_origin" in values:
                    primary = point(values["nuclear_origin"])
            elif line.startswith("parton ") and string_group is not None:
                values = fields(line)
                vertex = point(values.get("absolute_vertex"))
                if vertex is not None:
                    partons.setdefault(string_group, []).append(
                        Parton(int(values["index"]), int(values["pdg"]),
                               values.get("name", "").strip('"'), values.get("role", ""),
                               vertex, point(values.get("momentum")),
                               time(values.get("mass_GeV"))))
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
        raise ValueError("Expected an eHIJING fragmentation trace v2, v3 or v4 with event/settings headers")
    if not ended or not success:
        raise ValueError("The trace is incomplete or does not describe a successful event")

    trace = Trace(event, attempt, mode, vertices, strings=strings, partons=partons,
                  primary=primary, planes=planes, version=version, kappa=kappa, smear=smear)
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
            production_first=point(values.get("production_reference_first")),
            production_second=point(values.get("production_reference_second")),
            production_basis=values.get("production_basis", "legacy_breakup_pair"),
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
        hadron.final_production_first = point(values.get("stored_production_first"))
        hadron.final_production_second = point(values.get("stored_production_second"))
        hadron.prod_time = time(values.get("prod_time"))
    if not trace.hadrons:
        raise ValueError("No hadron vertices found in the trace")
    prepare_geometry(trace)
    return trace


def prepare_geometry(trace: Trace) -> None:
    """Convert native regional fractions to a continuous reference sheet.

    The two massless projections of an adjacent massive endpoint/gluon pair
    can rescale the gluon's energy. Its canonical directrix piece is still
    half the recorded gluon momentum, as used by PYTHIA's region offsets.
    Normalize those parallel bases before stitching regions. Project actual
    converted reference vertices, not uncorrected fragmentation fractions.
    """
    for (group, leg), plane in trace.planes.items():
        if not math.isfinite(plane.kappa) or plane.kappa <= 0:
            raise ValueError("Reference geometry requires positive finite string tension")
        native = plane.regions.copy()
        partons = trace.partons.get(group, [])
        if trace.strings.get(group, {}).get("topology") == "open" and len(partons) == plane.maximum + 2:
            normalized = {}
            for (pos, neg), (offset, plus, minus) in native.items():
                bases = []
                for p, vector in ((partons[pos], plus), (partons[-1 - neg], minus)):
                    canonical = scale(p.momentum, .5) if p.pdg == 21 and p.momentum is not None else vector
                    if canonical[0] <= 0:
                        plane.geometry_error = "Invalid directrix energy"
                        break
                    ratio = vector[0] / canonical[0]
                    if max(abs(a - ratio * b) for a, b in zip(vector, canonical)) > 1e-7 * max(1., vector[0]):
                        plane.geometry_error = "Gluon basis is not parallel to its recorded directrix"
                        break
                    bases.append(canonical)
                if len(bases) == 2:
                    normalized[(pos, neg)] = (offset, *bases)
            if not plane.geometry_error:
                plane.regions = normalized

        # Validate both ends of each shared edge, not only a hadron's path.
        for (pos, neg), (offset, plus, minus) in plane.regions.items():
            for neighbour, edge, tangent in (((pos - 1, neg), plus, minus),
                                              ((pos, neg - 1), minus, plus)):
                if neighbour not in plane.regions:
                    continue
                next_offset, next_plus, next_minus = plane.regions[neighbour]
                next_tangent = next_minus if neighbour[1] == neg else next_plus
                for a, b in ((add(offset, scale(edge, 1 / plane.kappa)), next_offset),
                             (tangent, next_tangent)):
                    if max(abs(x - y) for x, y in zip(a, b)) > 1e-7 * max(1., abs(a[0]), abs(b[0])):
                        plane.geometry_error = "Regional directrix edges do not join continuously"

        # Old unsmeared light-flavour traces already contain the exact converted
        # points in the stored breakup pairs. Per-hadron origins are subtracted
        # before choosing the shared plotting anchor.
        light = all(abs(p.pdg) not in (4, 5) for p in partons)
        if trace.smear is False and light:
            for h in trace.hadrons:
                if h.group != group or h.branch != leg or h.break_indices is None or h.origin is None:
                    continue
                for index, vertex in zip(h.break_indices, (h.first, h.second)):
                    if vertex is not None:
                        plane.effective.setdefault(index, add(vertex, scale(h.origin, -1)))

        for index in plane.break_roles:
            if index not in plane.effective:
                raw = plane.raw_breaks.get(index)
                if raw is None or raw[:2] not in native:
                    plane.invalid[index] = "special finalTwo point needs a converted reference record"
                    continue
                pos, neg, xp, xn = raw
                offset, plus, minus = native[(pos, neg)]
                value = scale(add(scale(plus, xp), scale(minus, xn)), 1 / plane.kappa)
                if dot(value, value) < 0:
                    total = scale(add(plus, minus), 1 / plane.kappa)
                    total2 = dot(total, total)
                    if total2 <= 0:
                        plane.invalid[index] = "degenerate spacetime correction"
                        continue
                    product = dot(total, value)
                    c = (-product + math.sqrt(max(0., product ** 2 - total2 * dot(value, value)))) / total2
                    correction = add(value, scale(total, c))
                    clamped = scale(add(scale(plus, min(1., max(0., xp))),
                                        scale(minus, min(1., max(0., xn)))), 1 / plane.kappa)
                    if (xp < 0 or xp > 1 or xn < 0 or xn > 1) and abs(value[0] - clamped[0]) < abs(value[0] - correction[0]):
                        correction = clamped
                    value = correction
                plane.effective[index] = add(offset, value)

            value = plane.effective[index]
            for (pos, neg), (offset, plus, minus) in plane.regions.items():
                product = dot(plus, minus)
                if product <= 0:
                    continue
                relative = scale(add(value, scale(offset, -1)), plane.kappa)
                xp, xn = dot(relative, minus) / product, dot(relative, plus) / product
                rebuilt = add(offset, scale(add(scale(plus, xp), scale(minus, xn)), 1 / plane.kappa))
                tolerance = 1e-7 * max(1., abs(value[0]))
                if (-1e-7 <= xp <= 1 + 1e-7 and -1e-7 <= xn <= 1 + 1e-7
                        and max(abs(a - b) for a, b in zip(value, rebuilt)) <= tolerance):
                    plane.breaks[index] = (plane.maximum - pos + min(1., max(0., xp)),
                                           plane.maximum - neg + min(1., max(0., xn)))
                    break
            else:
                plane.invalid[index] = "converted point lies outside the continuous reference regions"


def group_name(group: Group) -> str:
    if group == (-1, -1):
        return "Unassigned / multiple ancestor strings"
    return f"Pass {group[0]}, string {group[1]}"


def endpoint_curves(trace: Trace, group: Group) -> tuple[list[EndpointCurve], str]:
    """First outward/return excursion of an ideal unbroken massive string.

    In the input string CM frame, dp_parallel/dt = +/- kappa and
    dz/dt = p_parallel/E. Integrating gives dz = (E(t)-E(0))/force.
    Each clock starts at its recorded endpoint vertex. This is a diagnostic
    model: pair creation, recoil exchange and differing endpoint birth origins
    are not an evolution recorded by PYTHIA. No joining to saved F is imposed.
    See Ferreres-Sole & Sjostrand, arXiv:1808.04619, eq. (17).
    """
    partons = trace.partons.get(group, [])
    if trace.strings.get(group, {}).get("topology") != "open" or len(partons) != 2:
        return [], "massive model requires a two-parton open string (no gluon kinks/junctions)"
    endpoints = {p.role: p for p in partons}
    if set(endpoints) != {"positive_endpoint", "negative_endpoint"}:
        return [], "endpoint roles are missing"
    if trace.kappa is None or trace.kappa <= 0:
        return [], "positive string tension is missing"
    total = point(trace.strings[group].get("momentum"))
    if total is None or total[0] <= 0 or any(p.momentum is None for p in partons):
        return [], "input endpoint/string momentum is missing"
    beta = tuple(p / total[0] for p in total[1:])
    try:
        momenta = {role: boost(p.momentum, beta) for role, p in endpoints.items()}
    except ValueError:
        return [], "input string momentum is not timelike"
    rest_total = boost(total, beta)
    if max(abs(a - b) for a, b in zip(
            add(momenta["positive_endpoint"], momenta["negative_endpoint"]), rest_total)) > 1e-7 * max(1., rest_total[0]):
        return [], "input endpoint momenta do not sum to the recorded string momentum"
    positive = momenta["positive_endpoint"]
    magnitude = math.sqrt(sum(q * q for q in positive[1:]))
    if magnitude < 1e-10:
        return [], "input endpoints have no resolved outward momentum"
    direction = tuple(q / magnitude for q in positive[1:])
    inverse = tuple(-b for b in beta)
    curves = []
    for role, sign in (("positive_endpoint", 1), ("negative_endpoint", -1)):
        parton, p = endpoints[role], momenta[role]
        longitudinal = sum(q * n for q, n in zip(p[1:], direction))
        transverse = tuple(q - longitudinal * n for q, n in zip(p[1:], direction))
        if sign * longitudinal <= 0 or sum(q * q for q in transverse) > 1e-12 * max(1., magnitude ** 2):
            return [], "input endpoint momenta are not back-to-back in the string CM frame"
        invariant = p[0] ** 2 - sum(q * q for q in p[1:])
        if p[0] <= 0 or invariant < -1e-8 * max(1., p[0] ** 2):
            return [], "input endpoint is not an on-shell timelike/null state"
        mass = math.sqrt(max(0., invariant))
        if parton.mass is not None and abs(parton.mass ** 2 - invariant) > 1e-7 * max(1., p[0] ** 2):
            return [], "recorded endpoint mass and momentum disagree"
        force = -sign * trace.kappa
        initial_energy = math.hypot(mass, longitudinal)
        turning_time = abs(longitudinal) / trace.kappa
        # Sample the turn exactly; stop on return to the initial longitudinal
        # position. Continuing with the same force would not be a yo-yo cycle.
        path = []
        for step in range(201):
            elapsed = 2 * turning_time * step / 200
            q = longitudinal + force * elapsed
            energy = math.hypot(mass, q)
            displacement = (energy - initial_energy) / force
            delta = (elapsed, *(displacement * n for n in direction))
            path.append(add(parton.vertex, boost(delta, inverse)))
        curves.append(EndpointCurve(parton, mass, path, path[100]))
    return curves, ""


def collapse_reference(trace: Trace, hadron: Hadron) -> CollapseDiamond:
    """Effective massless yo-yo closing at O+p_h/kappa, after recoil exchange.

    Its axis is the positive input endpoint direction in the final hadron rest
    frame. The turns are model points, not sampled breakups or exact histories
    of the massive input partons. No stored event coordinate is changed.
    """
    if hadron.origin is None or hadron.momentum is None or trace.kappa is None or trace.kappa <= 0:
        raise ValueError("Collapse model needs its recorded origin, final momentum and tension")
    p = hadron.momentum
    mass2 = dot(p, p)
    if trace.mode != 2 or p[0] <= 0 or mass2 <= 0:
        raise ValueError("Collapse diamond requires a timelike final hadron in late mode")
    expected = add(hadron.origin, scale(p, 1 / trace.kappa))
    if max(abs(a - b) for a, b in zip(expected, hadron.saved)) > 1e-7 * max(1., abs(hadron.saved[0])):
        raise ValueError("Assigned collapse vertex is not O+p_h/kappa (smearing/heavy correction); input model retained")
    beta = tuple(q / p[0] for q in p[1:])
    endpoint = next((q.momentum for q in trace.partons.get(hadron.group, [])
                     if q.role == "positive_endpoint" and q.momentum is not None), None)
    direction = boost(endpoint, beta)[1:] if endpoint is not None else (0., 0., 1.)
    magnitude = math.sqrt(sum(q * q for q in direction))
    direction = tuple(q / magnitude for q in direction) if magnitude > 1e-10 else (0., 0., 1.)
    half_mass = math.sqrt(mass2) / 2
    inverse = tuple(-q for q in beta)
    plus = boost((half_mass, *(half_mass * q for q in direction)), inverse)
    minus = add(p, scale(plus, -1))
    turns = tuple(add(hadron.origin, scale(q, 1 / trace.kappa)) for q in (plus, minus))
    return CollapseDiamond(hadron, hadron.origin, turns,
                           [[hadron.origin, turn, hadron.saved] for turn in turns], plus)


def reference_origin(trace: Trace, hadron: Hadron) -> Vertex:
    """Use the recorded inherited origin; never average input birth events."""
    plane = trace.planes.get((hadron.group, hadron.branch))
    if plane is not None and plane.origin is not None:
        return plane.origin
    candidates = [h for h in trace.hadrons if h.group == hadron.group
                  and h.branch == hadron.branch and h.origin is not None]
    if candidates:
        first = min(candidates, key=lambda h: h.break_indices[0] if h.break_indices else h.index)
        return first.origin
    raise ValueError("No recorded inherited reference origin for this string leg")


def reference_hadron(trace: Trace, hadron: Hadron):
    plane = trace.planes.get((hadron.group, hadron.branch))
    if plane is None or hadron.break_indices is None:
        raise ValueError("No parameter-plane record for this hadron")
    ia, ib = hadron.break_indices
    if ia not in plane.breaks or ib not in plane.breaks:
        raise ValueError("Converted breakup has no valid continuous reference coordinates")
    a, b = plane.breaks[ia], plane.breaks[ib]
    if a[0] < b[0] - 1e-9 or a[1] > b[1] + 1e-9:
        raise ValueError("Breakup pair is not ordered across the parameter plane")
    meeting = (a[0], b[1])
    paths = [plane.path(a, meeting), plane.path(b, meeting)]
    first, second = plane.location(*a), plane.location(*b)
    formation = plane.location(*meeting)
    if any(max(abs(a - b) for a, b in zip(path[-1], formation)) > 1e-7 for path in paths):
        raise ValueError("The two recorded constituent paths do not meet continuously")
    momentum = scale(add(scale(formation, 2), scale(add(first, second), -1)), plane.kappa)
    origin = reference_origin(trace, hadron)
    return (add(origin, first), add(origin, second),
            add(origin, formation), momentum,
            [[add(origin, vertex) for vertex in path] for path in paths])


def reference_endpoints(trace: Trace, hadron: Hadron):
    """Original endpoint paths independent of a hadron's final-two solution.

    This prevents a missing hadron path from also hiding an original string
    arm. B0/Bn are massless-reference turns, not pair-creation vertices.
    """
    plane = trace.planes[(hadron.group, hadron.branch)]
    if trace.strings.get(hadron.group, {}).get("topology") != "open":
        return [], []
    boundary = sorted(i for i, role in plane.break_roles.items() if role == "boundary")
    if len(boundary) != 2:
        return [], ["Endpoint boundary labels are incomplete"]
    origin = reference_origin(trace, hadron)
    paths, omitted = [], []
    for index, role, start in ((boundary[0], "positive_endpoint", (float(plane.maximum), 0.)),
                               (boundary[-1], "negative_endpoint", (0., float(plane.maximum)))):
        try:
            uv = plane.breaks[index]
            if max(abs(x) for x in plane.location(*start)) > 1e-7:
                raise ValueError("Initial endpoint region does not start at the reference origin")
            path = plane.path(start, uv)
            # Continue along the endpoint characteristic to its adjacent
            # hadron's reference meeting, if that solution is reconstructible.
            for h in trace.hadrons:
                if h.group == hadron.group and h.branch == hadron.branch and h.break_indices is not None and index in h.break_indices:
                    try:
                        row = reference_hadron(trace, h)
                    except ValueError:
                        continue
                    side = h.break_indices.index(index)
                    absolute = [add(origin, v) for v in path]
                    paths.append((role, absolute + row[4][side][1:]))
                    break
            else:
                paths.append((role, [add(origin, v) for v in path]))
        except (KeyError, ValueError) as error:
            omitted.append(f"{role}: {error}")
    return paths, omitted


def place_labels(fig, ax, reserved=()):
    """Keep diagram labels inside the axes and avoid other labels/insets."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = ax.get_window_extent(renderer)
    occupied = [artist.get_window_extent(renderer) for artist in reserved]
    for label in ax.texts:
        if not hasattr(label, "xy"):
            continue
        if not hasattr(label, "_fragmentation_offset"):
            label._fragmentation_offset = label.get_position()
        original = label._fragmentation_offset
        candidates = [original] + [(sx * radius, sy * radius)
            for radius in (6, 12, 20, 30, 44, 60, 80)
            for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (0, -1))]
        best = None
        for offset in candidates:
            label.set_position(offset)
            label.set_ha("right" if offset[0] < 0 else "left")
            label.set_va("top" if offset[1] < 0 else "bottom")
            box = label.get_window_extent(renderer).expanded(1.05, 1.15)
            if bounds.contains(box.x0, box.y0) and bounds.contains(box.x1, box.y1):
                if best is None:
                    best = offset
                if not any(box.overlaps(other) for other in occupied):
                    best = offset
                    break
        label.set_position(best or original)
        label.set_ha("right" if label.get_position()[0] < 0 else "left")
        label.set_va("top" if label.get_position()[1] < 0 else "bottom")
        occupied.append(label.get_window_extent(renderer).expanded(1.05, 1.15))


def boundary_turn(trace, hadron, index):
    """Identify geometry boundary points without calling them pair creations."""
    plane = trace.planes.get((hadron.group, hadron.branch))
    return (trace.strings.get(hadron.group, {}).get("topology") != "closed"
            and plane is not None and plane.break_roles.get(index) == "boundary")


def rest_frame_beta(trace, group, total=None):
    """Validate the recorded momentum before requesting a string CM view."""
    if total is None:
        total = point(trace.strings.get(group, {}).get("momentum"))
    if total is None or not all(math.isfinite(q) for q in total) or total[0] <= 0 or dot(total, total) <= 0:
        raise ValueError("No positive-energy timelike string momentum; using the lab frame")
    return tuple(q / total[0] for q in total[1:])


def draw_diagram(trace, hadrons, axis, labels, title, colors, plt, Line2D,
                 frame="lab", duration=None, longitudinal=False, lund_boundaries=True,
                 collapse_model="both"):
    fig, ax = plt.subplots(figsize=(11.7, 8.3))
    component = {"x": 1, "y": 2, "z": 3, "longitudinal": 1}[axis]
    groups = sorted({h.group for h in hadrons})
    beta = (0., 0., 0.)
    origin = (0., 0., 0., 0.)
    direction = None
    show_lund = longitudinal or lund_boundaries
    collapses = []
    collapse_notes = []
    if show_lund and collapse_model in ("effective", "both"):
        for h in hadrons:
            if h.branch == "one-hadron-collapse":
                try:
                    collapses.append(collapse_reference(trace, h))
                except ValueError as error:
                    collapse_notes.append(str(error))
    collapse_groups = {model.hadron.group for model in collapses}
    if frame == "string-rest":
        if len(groups) != 1:
            raise ValueError("Select one string/pass with --string and --pass for a common string rest frame")
        total = point(trace.strings.get(groups[0], {}).get("momentum"))
        if axis == "longitudinal" and collapses and not any(key[0] == groups[0] for key in trace.planes):
            total = collapses[0].hadron.momentum
        beta = rest_frame_beta(trace, groups[0], total)
        origin = reference_origin(trace, hadrons[0]) if axis == "longitudinal" else trace.primary or origin

    if axis == "longitudinal":
        if frame != "string-rest" or len(groups) != 1:
            raise ValueError("A longitudinal string-axis view requires one string in its rest frame")
        # Use the geometry's positive light-cone direction. A two-hadron
        # mini-string can choose a decay axis different from the input parton
        # axis; its reference worldsheet follows that recorded decay geometry.
        positive = next((plane.regions[(0, plane.maximum)][1]
                         for (group, _), plane in trace.planes.items()
                         if group == groups[0] and (0, plane.maximum) in plane.regions), None)
        if positive is None:
            positive = collapses[0].positive if collapses else None
        if positive is None:
            positive = next((p.momentum for p in trace.partons.get(groups[0], [])
                             if p.role == "positive_endpoint" and p.momentum is not None), None)
        if positive is None:
            raise ValueError("The string has no recorded longitudinal reference direction")
        p = boost(positive, beta)
        magnitude = math.sqrt(sum(q * q for q in p[1:]))
        if magnitude < 1e-10:
            raise ValueError("The string has no resolved longitudinal reference direction")
        direction = tuple(q / magnitude for q in p[1:])

    def project(vector):
        if direction is None:
            return vector
        return (vector[0], sum(q * n for q, n in zip(vector[1:], direction)), 0., 0.)

    def position(vertex):
        return project(boost(add(vertex, scale(origin, -1)), beta))

    def line(vertices, color, linestyle="-", alpha=1., width=1.1):
        transformed = [position(vertex) for vertex in vertices]
        ax.plot([v[component] for v in transformed], [v[0] for v in transformed],
                color=color, linestyle=linestyle, linewidth=width, alpha=alpha)

    data = []
    skipped = 0
    for hadron in hadrons:
        if longitudinal:
            if hadron.group in collapse_groups:
                data.append((hadron, None, None, hadron.saved, hadron.momentum, []))
                continue
            try:
                first, second, formation, momentum, paths = reference_hadron(trace, hadron)
            except ValueError:
                skipped += 1
                continue
        else:
            first, second, formation, momentum, paths = (
                hadron.first, hadron.second, hadron.saved, hadron.momentum, [])
        data.append((hadron, first, second, formation, momentum, paths))
    boundaries = []
    area = []
    geometry_notes = []
    reference_data = data if longitudinal else []
    skipped_reference = 0
    seen_planes = set()
    if show_lund:
        from matplotlib.collections import PolyCollection
        for hadron in hadrons:
            key = (hadron.group, hadron.branch)
            if not longitudinal and key in trace.planes:
                try:
                    reference_data.append((hadron, *reference_hadron(trace, hadron)))
                except ValueError:
                    skipped_reference += 1
            if key not in trace.planes or key in seen_planes:
                continue
            seen_planes.add(key)
            origin_ref = reference_origin(trace, hadron)
            endpoint_paths, omitted = reference_endpoints(trace, hadron)
            boundaries.extend((hadron.group, role, path) for role, path in endpoint_paths)
            geometry_notes.extend(omitted)
            try:
                cells = trace.planes[key].string_cells()
            except ValueError as error:
                geometry_notes.append(str(error))
            else:
                area.extend((hadron.group, [add(origin_ref, v) for v in cell]) for cell in cells)
        polygons, facecolors = [], []
        for group, cell in area:
            values = [position(v) for v in cell]
            polygons.append([(v[component], v[0]) for v in values])
            facecolors.append(colors[group])
        for model in collapses:
            cell = [model.origin, model.turns[0], model.hadron.saved, model.turns[1]]
            values = [position(v) for v in cell]
            polygons.append([(v[component], v[0]) for v in values])
            facecolors.append(colors[model.hadron.group])
        if polygons:
            ax.add_collection(PolyCollection(polygons, facecolors=facecolors, edgecolors="none",
                                            alpha=0.16 if longitudinal else 0.10, zorder=0))
            ax.autoscale_view()
    if longitudinal and not data and not boundaries and not area:
        ax.set_axis_off()
        ax.set_title(title)
        ax.text(0.05, 0.65, "No reconstructable longitudinal constituent paths for this selection.\n"
                "Missing/invalid final-two parameter coordinates or discontinuous regions\n"
                "are not replaced by straight-line interpolation.\n"
                f"Omitted hadrons: {skipped}", transform=ax.transAxes)
        return fig
    models = {}
    omitted_models = {}
    for group in groups:
        if not longitudinal or (collapse_model == "both" and group in collapse_groups):
            if group in collapse_groups and collapse_model != "both":
                continue
            # Complete connected Lund boundaries take precedence over the
            # independent unbroken-endpoint model on saved-vertex pages.
            roles = {role for g, role, _ in boundaries if g == group}
            if {"positive_endpoint", "negative_endpoint"} <= roles:
                continue
            curves, reason = endpoint_curves(trace, group)
            if curves:
                models[group] = curves
            else:
                omitted_models[group] = reason
    times = [position(row[3])[0] for row in data]
    if not times:
        times = [position(v)[0] for _, _, path in boundaries for v in path]
        times.extend(position(v)[0] for _, cell in area for v in cell)
    primary_time = position(trace.primary)[0] if trace.primary is not None else min(times)
    end_time = max(times) + (duration if duration is not None else max(1., 0.25 * (max(times) - primary_time)))
    for group, curves in models.items():
        for curve in curves:
            color = colors[group]
            line(curve.path, color, linestyle=":", width=1.5)
            start, turn = position(curve.path[0]), position(curve.turn)
            ax.plot(start[component], start[0], "D", color=color,
                    markerfacecolor="none", markersize=5, zorder=4)
            ax.plot(turn[component], turn[0], "^", color=color,
                    markerfacecolor=color, markersize=5, zorder=4)
            if labels:
                ax.annotate(f"P{curve.parton.index}", (start[component], start[0]), xytext=(4, -12),
                            textcoords="offset points", fontsize=7, color=color)
    seen_breakups = set()
    seen_turns = False
    if show_lund and not longitudinal:
        for hadron, first, second, formation, momentum, paths in reference_data:
            color = colors[hadron.group]
            for path in paths:
                line(path, color, width=1.3, alpha=0.85)
            vertex = position(formation)
            ax.plot(vertex[component], vertex[0], "o", color="purple",
                    markerfacecolor="none", markersize=8, zorder=5)
            if labels:
                ax.annotate(f"RF{hadron.index}", (vertex[component], vertex[0]), xytext=(4, -10),
                            textcoords="offset points", fontsize=7, color=color)
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
                index = hadron.break_indices[side] if hadron.break_indices is not None else None
                turn = boundary_turn(trace, hadron, index)
                seen_turns = seen_turns or turn
                ax.plot(vertex[component], vertex[0], "^" if turn else "o", color="green",
                        markerfacecolor="green", markersize=6, alpha=alpha, zorder=5)
                if labels and hadron.break_indices is not None:
                    index = hadron.break_indices[side]
                    plane = trace.planes.get((hadron.group, hadron.branch))
                    mark = "!" if show_lund and plane is not None and index in plane.invalid else ""
                    ax.annotate(f"{'T' if turn else 'B'}{index}{mark}",
                                (vertex[component], vertex[0]), xytext=(-5, -10),
                                textcoords="offset points", fontsize=7, color="green")
                seen_breakups.add(key)
        vertex = position(formation)
        ax.plot(vertex[component], vertex[0], "o", color="purple",
                markerfacecolor="purple", markersize=6, alpha=alpha, zorder=6)
        # Only exported final hadrons are extrapolated indefinitely; no invented
        # decay/interaction lifetime is assigned to nonfinal particles.
        if momentum is not None and hadron.output_id is not None:
            p = project(boost(momentum, beta))
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
            if not longitudinal and hadron.first is not None and hadron.second is not None and hadron.saved[0] < max(hadron.first[0], hadron.second[0]) - 1e-8:
                label += " !"
            if hadron.output_id is not None:
                label += f" / ID {hadron.output_id}"
            ax.annotate(label, (vertex[component], vertex[0]), xytext=(4, 4),
                        textcoords="offset points", fontsize=7, color=color, alpha=alpha)
    for group, role, path in boundaries:
        color = colors[group]
        line(path, color, width=2.6)
        if labels and len(path) > 1:
            parton = next((p for p in trace.partons.get(group, []) if p.role == role), None)
            name = f"P{parton.index} ({parton.name or parton.pdg})" if parton else role.replace("_", " ")
            # Label the outward boundary halfway to its first turn.
            location = position(scale(add(path[0], path[1]), 0.5))
            ax.annotate(name, (location[component], location[0]), xytext=(6, 4),
                        textcoords="offset points", fontsize=8, color=color)
    for model in collapses:
        color = colors[model.hadron.group]
        for side, path in enumerate(model.paths):
            line(path, color, linestyle="-.", width=2.3)
            turn = position(model.turns[side])
            ax.plot(turn[component], turn[0], "^", color=color, markersize=6, zorder=5)
            if labels:
                ax.annotate(f"CT{model.hadron.index}{'+' if side == 0 else '-'}",
                            (turn[component], turn[0]), xytext=(4, 4),
                            textcoords="offset points", fontsize=7, color=color)
        start = position(model.origin)
        ax.plot(start[component], start[0], "o", color=color,
                markerfacecolor="white", markersize=5, zorder=5)
        if labels:
            origin_label = "collapse origin / production" if model.hadron.production_basis == "collapse_origin" else "collapse origin"
            ax.annotate(origin_label, (start[component], start[0]), xytext=(4, -12),
                        textcoords="offset points", fontsize=7, color=color)
    if show_lund:
        for group, leg in seen_planes:
            seed = next(h for h in hadrons if h.group == group and h.branch == leg)
            origin_ref = reference_origin(trace, seed)
            plane = trace.planes[(group, leg)]
            for index, relative in plane.effective.items():
                breakup = add(origin_ref, relative)
                key = (group, breakup)
                if key in seen_breakups:
                    continue
                vertex = position(breakup)
                turn = boundary_turn(trace, seed, index)
                seen_turns = seen_turns or turn
                ax.plot(vertex[component], vertex[0], "^" if turn else "o", color="green",
                        markerfacecolor="green" if longitudinal else "none",
                        markersize=6 if longitudinal else 8, zorder=5)
                if labels:
                    label = ("T" if turn else "B") + str(index)
                    if not longitudinal:
                        label = "R" + label
                    if index in plane.invalid:
                        label += "!"
                    ax.annotate(label, (vertex[component], vertex[0]), xytext=(-5, -10),
                                textcoords="offset points", fontsize=7, color="green")
                seen_breakups.add(key)
            vertex = position(origin_ref)
            ax.plot(vertex[component], vertex[0], "o", color=colors[group],
                    markerfacecolor="white", markersize=5, zorder=5)
            if labels:
                origin_label = "string origin" if longitudinal else "reference origin"
                if any(h.group == group and h.branch == leg
                       and h.production_basis in ("string_origin_and_breakup", "string_origin") for h in hadrons):
                    origin_label += " / end production"
                ax.annotate(origin_label,
                            (vertex[component], vertex[0]), xytext=(6, -12),
                            textcoords="offset points", fontsize=7, color=colors[group])
    if trace.primary is not None:
        primary = position(trace.primary)
        ax.plot(primary[component], primary[0], "*", color="yellow", markerfacecolor="yellow",
                markeredgecolor="goldenrod", markersize=14, zorder=10)
        if labels:
            ax.annotate("primary", (primary[component], primary[0]), xytext=(8, -12),
                        textcoords="offset points", fontsize=7, color="goldenrod")
    saved_label = ("Assigned collapse formation" if collapses else "Constituent meeting / formation") if longitudinal else (
        "Saved formation vertex" if trace.mode == 2 else "Saved hadron vertex")
    handles = [
        Line2D([], [], color="purple", marker="o", linestyle="none", label=saved_label),
        Line2D([], [], color="yellow", marker="*", markeredgecolor="goldenrod",
               markersize=12, linestyle="none", label="Primary vertex"),
        Line2D([], [], color="black", linestyle="--", label="Hadron worldline (p/E)"),
    ]
    if seen_planes or any(row[1] is not None or row[2] is not None for row in data):
        handles.insert(0, Line2D([], [], color="green", marker="o", linestyle="none", label="Breakup (pair creation)"))
    if seen_turns:
        handles.insert(1, Line2D([], [], color="green", marker="^", linestyle="none", label="T: boundary turn (no breakup)"))
    if show_lund and seen_planes and (boundaries or reference_data or area):
        from matplotlib.patches import Patch
        handles.extend([
            Line2D([], [], color="black", linewidth=2.6, label="Original endpoint boundary"),
            Line2D([], [], color="black", linewidth=1.1, label="Breakup constituent boundary"),
            Line2D([], [], color="black", marker="o", markerfacecolor="white", linestyle="none", label="Shared string reference origin"),
        ])
        if area:
            handles.append(Patch(facecolor="grey", alpha=0.16, label="Verified reference string area"))
        if not longitudinal:
            handles.extend([
                Line2D([], [], color="green", marker="o", markerfacecolor="none", linestyle="none", label="RB: reference breakup"),
                Line2D([], [], color="purple", marker="o", markerfacecolor="none", linestyle="none", label="RF: reference meeting"),
            ])
    if models:
        handles.extend([
            Line2D([], [], color="black", linestyle=":", linewidth=1.5, label="Massive input endpoint (model)"),
            Line2D([], [], color="black", marker="D", markerfacecolor="none", linestyle="none", label="Input constituent start (recorded)"),
            Line2D([], [], color="black", marker="^", linestyle="none", label="Endpoint turn (model)"),
        ])
        if len(groups) == 1:
            for curve in models[groups[0]]:
                p = curve.parton
                handles.append(Line2D([], [], color=colors[groups[0]], linestyle=":",
                    label=f"P{p.index}: {p.name or p.pdg}, m={curve.mass:.3g} GeV"))
    if collapses:
        handles.extend([
            Line2D([], [], color="black", linestyle="-.", linewidth=2.3, label="Collapse Lund diamond (effective)"),
            Line2D([], [], color="black", marker="^", linestyle="none", label="CT: model turn, not a breakup"),
        ])
        if not seen_planes:
            from matplotlib.patches import Patch
            handles.append(Patch(facecolor="grey", alpha=0.16, label="Effective collapse string area"))
    for group in groups:
        handles.append(Line2D([], [], color=colors[group], linewidth=2, label=group_name(group)))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    axis_label = "effective collapse axis" if collapses and not seen_planes else "string reference CM axis"
    ax.set_xlabel(f"z_parallel [fm] ({axis_label})" if direction is not None else f"{axis} [fm]")
    ax.set_ylabel("t [fm/c]")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.2)
    ax.margins(0.15)
    display_frame = ("final-hadron-rest" if longitudinal and collapses and not seen_planes and frame == "string-rest"
                     else "input-string-rest" if frame == "string-rest" and not longitudinal else frame)
    ax.set_title(title + f"\nEvent {trace.event}, attempt {trace.attempt}, mode {trace.mode}; frame: {display_frame}")
    notes = "P/H = PYTHIA parton/hadron index; ID = OSCAR output_ID. Faded points: not exported.\n"
    if seen_turns:
        notes += "Green circles B/RB create pairs; triangles T/RT are geometric turns. New ordinary end production assignments use the origin.\n"
    if longitudinal:
        if seen_planes:
            notes += "Lund massless-reference picture: bold original endpoints; thin breakup constituents; verified string area is shaded.\n"
            notes += "Shading excludes the future of pair creations. Transverse tunnelling/smearing and massive-endpoint corrections are excluded.\n"
            notes += "Purple meeting points and outgoing hadron slopes belong to this reference picture; see saved-vertex pages for recorded formation."
        else:
            notes += "Effective one-hadron collapse model: no sampled breakup pair or recoil-exchange trajectory is available."
        notes += "\nReference origin is the recorded inherited origin; saved metadata is unchanged."
        if skipped:
            notes += f"\n{skipped} hadron(s) omitted: missing/invalid parameter-plane path; no trajectory was interpolated."
        if geometry_notes:
            notes += "\nIncomplete geometry: unverified paths/areas are omitted; B! marks a converted point outside the reference domain."
    else:
        notes += "Recorded vertices; free hadron worldlines begin at saved formation points.\n"
        if show_lund and seen_planes:
            notes += "Lund overlay: bold original endpoints, thin breakup constituents and shaded surviving string (massless reference).\n"
            notes += "Hollow RB/RF points belong to that reference; filled circles show recorded vertices and may differ.\n"
            notes += "Reference paths use the recorded inherited origin; B! marks a converted point outside the reference domain.\n"
            if skipped_reference or geometry_notes:
                notes += f"Incomplete reference geometry: {skipped_reference} hadron path(s), {len(geometry_notes)} boundary/area issue(s) omitted.\n"
        if show_lund:
            missing = len(set(groups) - {group for group, _ in seen_planes} - collapse_groups)
            if missing:
                notes += f"No Lund parameter plane for {missing} group(s); only the available endpoint model is shown there.\n"
    if models:
        notes += "\nDotted input curves: unbroken constant-tension model, from each recorded start through its first turn and return."
        notes += "\nStarts mark input constituent availability; turns do not create constituents. Recoil exchange/pair creation are not modelled."
        notes += "\nCurves follow the input CM force and are not fitted to saved formation points or full PYTHIA histories."
    if omitted_models:
        notes += f"\nMassive model unavailable for {len(omitted_models)} string group(s); unsupported geometry or missing/invalid input."
    if collapses:
        notes += "\nCollapse diamond: final p_h and assigned origin define an effective massless string closing at saved F=O+p_h/kappa."
        notes += "\nIts axis follows the positive input endpoint in the final hadron rest frame; it is not a pre-collapse recoil history."
        notes += "\nThe diamond origin is an effective common start, not a measured constituent birth; CT marks reversal, purple F hadron formation."
        if len(collapses) == 1 and len(groups) == 1:
            mass = math.sqrt(dot(collapses[0].hadron.momentum, collapses[0].hadron.momentum))
            notes += f"\nEffective final mass: {mass:.6g} GeV; proper extent m_h/kappa = {mass / trace.kappa:.6g} fm/c."
    if collapse_notes:
        notes += "\nSome collapse assignments do not support the effective late diamond; their available input endpoint model is shown."
    if any(h.first is not None and h.second is not None and h.saved[0] < max(h.first[0], h.second[0]) - 1e-8 for h in hadrons):
        notes += "\nH!: stored lab-frame formation precedes an associated geometric point; no causal constituent connection is implied."
    if not trace.vertices:
        notes += "\nVertex generation is OFF; saved coordinates may be default zeros."
    elif trace.mode != 2:
        notes += "\nThe saved vertex is not necessarily the late formation point in this mode."
    notes += "\nMain axes share limits with event pages in this frame/projection; endpoint-detail insets use a local zoom."
    if axis == "longitudinal":
        notes += "\nLongitudinal pages share numerical scales; each string uses its own rest frame and reference axis."
    elif frame == "string-rest":
        notes += "\nRest plots use each input string's CM and the primary origin; different strings share scales, not a physical frame."
    fig.text(0.06, 0.025, notes, fontsize=7)
    bottom = max(0.18, 0.075 + 0.014 * (notes.count("\n") + 1))
    fig.subplots_adjust(left=0.08, right=0.70, bottom=min(0.40, bottom), top=0.88)
    if len(models) == 1 and len(groups) == 1:
        curves = models[groups[0]]
        vertices = [position(v) for curve in curves for v in curve.path]
        xmin, xmax = min(v[component] for v in vertices), max(v[component] for v in vertices)
        tmin, tmax = min(v[0] for v in vertices), max(v[0] for v in vertices)
        if tmax - tmin < 0.3 * (end_time - min(primary_time, tmin)):
            detail = ax.inset_axes([0.06, 0.58, 0.40, 0.34])
            color = colors[groups[0]]
            for curve in curves:
                values = [position(v) for v in curve.path]
                detail.plot([v[component] for v in values], [v[0] for v in values],
                            color=color, linestyle=":", linewidth=1.5)
                start, turn = position(curve.path[0]), position(curve.turn)
                detail.plot(start[component], start[0], "D", color=color, markerfacecolor="none", markersize=4)
                detail.plot(turn[component], turn[0], "^", color=color, markersize=4)
                if labels:
                    detail.annotate(f"P{curve.parton.index}", (start[component], start[0]), xytext=(4, -10),
                                    textcoords="offset points", fontsize=7, color=color)
            xpad, tpad = max(0.02, 0.3 * (xmax - xmin)), max(0.02, 0.3 * (tmax - tmin))
            # A near-transverse projection can otherwise shrink the equal-scale
            # inset into an unreadable sliver. Widen its spatial padding while
            # retaining equal spacetime scales and the recorded trajectory.
            xpad = max(xpad, 0.5 * ((tmax - tmin) + 2 * tpad - (xmax - xmin)))
            detail.set_xlim(xmin - xpad, xmax + xpad)
            detail.set_ylim(tmin - tpad, tmax + tpad)
            detail.set_aspect("equal", adjustable="box")
            detail.set_xlabel(f"{axis} [fm]", fontsize=7)
            detail.set_ylabel("t [fm/c]", fontsize=7)
            detail.tick_params(labelsize=7)
            detail.grid(alpha=0.2)
            detail.set_title("Endpoint detail (same frame)", fontsize=8)
    return fig


def share_axis_limits(pages, labels):
    """Use the union of main-axes data within each frame/projection family.

    Longitudinal pages have independent CM frames; sharing their numerical
    extent gives a common comparison scale without overlaying their coordinates.
    Insets keep their explicit zoom. Box adjustment preserves identical limits
    even when the page notes leave different amounts of plotting space.
    """
    families = {}
    for fig, frame, axis in pages:
        ax = fig.axes[0]
        if ax.axison and all(math.isfinite(v) for v in ax.dataLim.extents):
            families.setdefault((frame, axis), []).append((fig, ax))
    for members in families.values():
        xmin = min(ax.dataLim.xmin for _, ax in members)
        xmax = max(ax.dataLim.xmax for _, ax in members)
        tmin = min(ax.dataLim.ymin for _, ax in members)
        tmax = max(ax.dataLim.ymax for _, ax in members)
        xpad = max(0.05, 0.15 * (xmax - xmin))
        tpad = max(0.05, 0.15 * (tmax - tmin))
        for fig, ax in members:
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlim(xmin - xpad, xmax + xpad)
            ax.set_ylim(tmin - tpad, tmax + tpad)
            if labels:
                for detail in ax.child_axes:
                    place_labels(fig, detail)
                place_labels(fig, ax, ax.child_axes)


def time_tables(trace, hadrons, plt, frame="lab"):
    """Tabulate recorded times; recompute the minimum after boosting breakups."""
    betas = {}
    origin = (0., 0., 0., 0.)
    subtitle = "lab"
    if frame == "string-rest":
        groups = {h.group for h in hadrons}
        betas = {group: rest_frame_beta(trace, group) for group in groups}
        origin = trace.primary or origin
        subtitle = ("input string rest frame, " + group_name(hadrons[0].group)
                    if len(groups) == 1 else "each row in its own input-string rest frame")

    def transformed_time(vertex, group):
        return boost(add(vertex, scale(origin, -1)), betas.get(group, (0., 0., 0.)))[0]

    rows = []
    for hadron in sorted(hadrons, key=lambda h: (h.group, h.index)):
        final = hadron.final_saved or hadron.saved
        production = hadron.prod_time
        if frame != "lab" and production is not None:
            first = hadron.final_production_first or hadron.production_first or hadron.final_first or hadron.first
            second = hadron.final_production_second or hadron.production_second or hadron.final_second or hadron.second
            # The earliest production reference is frame dependent. A scalar time alone
            # cannot supply a rest-frame production time.
            production = (min(transformed_time(first, hadron.group), transformed_time(second, hadron.group))
                          if first is not None and second is not None else None)
        rows.append([
            f"{hadron.group[0]}/{hadron.group[1]}" if hadron.group != (-1, -1) else "unassigned",
            str(hadron.index), str(hadron.output_id) if hadron.output_id is not None else "-",
            f"{hadron.name or hadron.pdg} ({hadron.pdg})",
            f"{production:.8g}" if production is not None else "unavailable",
            f"{transformed_time(final, hadron.group):.8g}",
        ])
    headers = ["Pass/string", "H", "OSCAR ID", "Particle (PDG)", "prod_time",
               "form_time" if trace.mode == 2 else "vertex t"]
    for start in range(0, len(rows), 32):
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ax.set_axis_off()
        ax.set_title(f"Event {trace.event}: particle times [fm/c]\n{subtitle}; rows {start + 1}-{min(start + 32, len(rows))}", pad=20)
        page_rows = rows[start:start + 32]
        height = (len(page_rows) + 1) / 36
        table = ax.table(cellText=page_rows, colLabels=headers, cellLoc="center",
                         colWidths=[0.13, 0.06, 0.09, 0.32, 0.20, 0.20],
                         bbox=[0, 1 - height, 1, height])
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("0.8")
            if row == 0:
                cell.set_facecolor("0.9")
        fig.text(0.08, 0.05,
                 "form_time uses the final particle vertex when available, otherwise the fragmentation assignment; mode 2 stores formation.\n"
                 "Unavailable is distinct from zero. Older traces retain their historical production-time assignments.\n"
                 "Rest-frame prod_time uses full production references (origins/breakups), not a scalar time boost.\n"
                 "Rest tables use the input string CM and primary origin, like saved-vertex rest plots. Effective diamond pages use the final hadron CM.\n"
                 "Rows for different strings have different rest frames; this table does not define a common event CM.\n"
                 "OSCAR ID '-' means not exported. Spectators are excluded. Reference meeting times can differ from saved formation times.", fontsize=8)
        fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.88)
        yield fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="event_XXXXXXXX.fragmentation file")
    parser.add_argument("-o", "--output", type=Path, help="PDF path (default: input with .pdf extension)")
    parser.add_argument("--axis", choices=["x", "y", "z"], default="z", help="Spatial projection (default: z)")
    parser.add_argument("--string", type=int, help="Restrict to a string index")
    parser.add_argument("--pass", dest="pass_number", type=int, help="Restrict to a hadronization pass")
    parser.add_argument("--no-labels", action="store_true", help="Omit particle labels on diagrams")
    parser.add_argument("--overview-only", action="store_true", help="Save only overview diagrams, without per-string pages or tables")
    parser.add_argument("--frame", choices=["both", "lab", "string-rest"], default="both",
                        help="Saved-vertex frames (default: both); a multi-string overview or unavailable rest frame uses lab only")
    parser.add_argument("--lund-view", choices=["string-rest", "projection"],
                        help="Lund pages: each string's CM longitudinal axis, or selected frame/axis projections (default: CM unless --frame lab)")
    parser.add_argument("--table", action=argparse.BooleanOptionalAction, default=True,
                        help="Append particle-time tables in the requested frames (default: enabled)")
    parser.add_argument("--lund-boundaries", action=argparse.BooleanOptionalAction, default=True,
                        help="Overlay connected Lund reference boundaries on overview/saved-vertex pages (default: enabled)")
    parser.add_argument("--collapse-model", choices=["both", "effective", "input"], default="both",
                        help="Collapse endpoints: both models (default), just the effective late diamond, or just the massive input excursion")
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
        geometry_groups = {h.group for h in hadrons if (h.group, h.branch) in trace.planes}
        collapse_groups = set()
        if args.collapse_model in ("effective", "both"):
            for h in hadrons:
                if h.branch == "one-hadron-collapse":
                    try:
                        collapse_reference(trace, h)
                    except ValueError:
                        continue
                    collapse_groups.add(h.group)
        rest_unavailable = {}
        for group in groups:
            try:
                rest_frame_beta(trace, group)
            except ValueError as error:
                rest_unavailable[group] = str(error)
        requested_frames = ("lab", "string-rest") if args.frame == "both" else (args.frame,)
        def frames_for(selection):
            if len(selection) != 1 or selection[0] in rest_unavailable:
                return ("lab",)
            return requested_frames
        lund_view = args.lund_view or ("projection" if args.frame == "lab" else "string-rest")
        palette = plt.get_cmap("tab10" if len(groups) <= 10 else "tab20")
        colors = {group: palette(index % palette.N) for index, group in enumerate(groups)}
        pages = []
        try:
            overview_title = ("Lund boundaries and saved vertices" if args.lund_boundaries and (geometry_groups or collapse_groups)
                              else "Saved vertices, massive endpoints and hadron worldlines")
            for frame in frames_for(groups):
                fig = draw_diagram(trace, hadrons, args.axis, not args.no_labels,
                                   overview_title, colors, plt, Line2D,
                                   frame, args.duration, lund_boundaries=args.lund_boundaries,
                                   collapse_model=args.collapse_model)
                pages.append((fig, frame, args.axis))
            if not args.overview_only:
                for group in groups:
                    subset = [h for h in hadrons if h.group == group]
                    info = trace.strings.get(group, {})
                    title = group_name(group)
                    if info:
                        title += f" - {info.get('branch', '')}, {info.get('topology', '')}, input mass {float(info['mass_GeV']):.6g} GeV"
                    if any(key[0] == group for key in trace.planes) or group in collapse_groups:
                        cm_view = lund_view == "string-rest" and group not in rest_unavailable
                        lund_axis = "longitudinal" if cm_view else args.axis
                        lund_frames = ("string-rest",) if cm_view else frames_for([group])
                        collapse_title = ("Collapse: effective diamond and massive input\n"
                                          if args.collapse_model == "both" else "Effective collapse Lund diamond\n")
                        for lund_frame in lund_frames:
                            fig = draw_diagram(trace, subset, lund_axis, not args.no_labels,
                                               (collapse_title if group in collapse_groups else
                                                "Lund string boundaries (massless reference)\n") + title,
                                               colors, plt, Line2D, lund_frame, args.duration,
                                               longitudinal=True, collapse_model=args.collapse_model)
                            pages.append((fig, lund_frame, lund_axis))
                    if len(groups) > 1:
                        for frame in frames_for([group]):
                            fig = draw_diagram(trace, subset, args.axis, not args.no_labels,
                                               "Saved vertices: " + title, colors, plt, Line2D, frame, args.duration,
                                               lund_boundaries=args.lund_boundaries, collapse_model=args.collapse_model)
                            pages.append((fig, frame, args.axis))
                if args.table:
                    if args.frame in ("lab", "both") or len(groups) != 1 or rest_unavailable:
                        pages.extend((fig, "lab", None) for fig in time_tables(trace, hadrons, plt))
                    if args.frame in ("both", "string-rest"):
                        rest_hadrons = [h for h in hadrons if h.group not in rest_unavailable]
                        if rest_hadrons:
                            pages.extend((fig, "string-rest", None)
                                         for fig in time_tables(trace, rest_hadrons, plt, "string-rest"))
            share_axis_limits(pages, not args.no_labels)
            with PdfPages(output, metadata={"Title": f"eHIJING event {trace.event} fragmentation",
                                            "Subject": "Hadronization spacetime diagram"}) as pdf:
                for fig, _, _ in pages:
                    pdf.savefig(fig)
        finally:
            for fig, _, _ in pages:
                plt.close(fig)
    except ImportError:
        parser.error("matplotlib is required: python3 -m pip install matplotlib")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(f"Saved {output} ({len(hadrons)} hadrons, {len(groups)} string/pass groups)")
    if len(groups) > 1 and args.frame != "lab":
        print("Multi-string overview uses lab only; individual strings use their own rest frames when available.")
    for group, reason in rest_unavailable.items():
        print(f"{group_name(group)}: {reason}")
    if args.lund_boundaries:
        print(f"Lund boundary overlay enabled: {len(geometry_groups)} group(s) with parameter-plane geometry; "
              f"{len(collapse_groups)} effective collapse diamond(s).")
    for (group, leg), plane in trace.planes.items():
        if group not in groups:
            continue
        if plane.geometry_error:
            print(f"{group_name(group)}, {leg}: {plane.geometry_error}; inconsistent reference paths are omitted.")
        for index, reason in plane.invalid.items():
            print(f"{group_name(group)}, {leg}: B{index}: {reason}; no trajectory is fabricated.")
    for group in groups:
        _, reason = endpoint_curves(trace, group)
        if reason:
            print(f"{group_name(group)}: massive endpoint model omitted: {reason}")
    if args.collapse_model in ("effective", "both"):
        for hadron in hadrons:
            if hadron.branch == "one-hadron-collapse" and hadron.group not in collapse_groups:
                try:
                    collapse_reference(trace, hadron)
                except ValueError as error:
                    print(f"{group_name(hadron.group)}: effective collapse diamond omitted: {error}")
    if not trace.planes and not collapse_groups:
        print("No parameter plane: ordinary Lund reference paths require v3/v4 geometry; massive input endpoints remain available.")


if __name__ == "__main__":
    main()
