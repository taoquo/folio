"""The one place connector geometry is defined, checked, and repaired.

Every family lays connectors out differently -- architecture runs an A* router over eight
ranked candidates, flowcharts fill row corridors, structural graphs fan out from layered
bands -- and that variety is worth keeping. What is not worth keeping is each family also
owning its own copy of the rules those layouts must satisfy. That is how flowcharts ended up
without bridge hops for a whole release while the sibling implementation next to it carried a
comment explaining why they were needed.

So layout stays per family and the contract lives here:

* :func:`collect_connectors` gives every family's connectors one shape, whether they are
  ``SceneEdge`` objects or loose primitives.
* :func:`check_contract` is wired into the single finalize step every kind passes through, so
  a new diagram type inherits the gate instead of having to remember it.
* :func:`route_is_clear`, :func:`blocks_lane` and :func:`assign_bridges` are the primitives a
  layout calls to satisfy the contract rather than reimplement it.

The thresholds mirror references/drawing-architecture.md; when the spec moves, this is the
only module that has to follow.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from ..layout.models import LayoutBox

Point = tuple[int, int]
Segment = tuple[Point, Point]


@dataclass(frozen=True)
class ConnectorContract:
    """Thresholds the spec states in prose, in one machine-readable place."""

    #: A run may touch an unrelated node's outline this far before it reads as attached to it.
    graze_tolerance: int = 16
    #: Attach points on one face must stay this far apart to stay tellable apart.
    attach_separation: int = 12
    #: Elbow radius, so a run shorter than twice this cannot show its corner.
    elbow_radius: int = 8
    #: Padding used when testing whether a run clears a node.
    node_padding: int = 4


DEFAULT_CONTRACT = ConnectorContract()

#: Primitive id prefixes that carry a connector between two nodes.
CONNECTOR_PREFIXES = ("link:", "relationship-line:", "message-line:", "arc:")
#: Primitive id fragments that carry an arrowhead or notation marker, not a connector body.
MARKER_FRAGMENTS = ("-head:", "arrow:", "-marker:")
#: Primitives that structure the canvas rather than connect nodes. Messages legitimately
#: terminate on a sequence lifeline, and a chart's own series is not a connector at all.
GUIDE_PREFIXES = (
    "lifeline", "timeline-axis", "quadrant-x", "quadrant-y", "quadrant-frame",
    "preferred-regi", "grid", "axis", "baseline", "tick", "reference", "separator", "band",
)
SERIES_PREFIXES = ("line:", "series:", "point:", "bar:", "candle:", "segment:", "slice:")


def _is(prefixes: Iterable[str], value: str) -> bool:
    return any(value.startswith(prefix) for prefix in prefixes)


def is_guide(primitive_id: str) -> bool:
    return _is(GUIDE_PREFIXES, primitive_id) or _is(SERIES_PREFIXES, primitive_id)


def is_marker(primitive_id: str) -> bool:
    return any(fragment in primitive_id for fragment in MARKER_FRAGMENTS)


def is_connector(primitive_id: str) -> bool:
    return _is(CONNECTOR_PREFIXES, primitive_id)


@dataclass(frozen=True)
class Connector:
    """One connector, however its family chose to draw it."""

    id: str
    points: tuple[Point, ...]
    source: str | None
    target: str | None
    arrow: tuple[Point, ...] | None
    curved: bool = False

    @property
    def segments(self) -> tuple[Segment, ...]:
        return tuple((a, b) for a, b in zip(self.points, self.points[1:]) if a != b)

    @property
    def final_run(self) -> int:
        if len(self.points) < 2:
            return 0
        last, previous = self.points[-1], self.points[-2]
        return abs(last[1] - previous[1]) if last[0] == previous[0] else abs(last[0] - previous[0])

    @property
    def arrow_extent(self) -> int:
        if not self.arrow:
            return 0
        width = max(p[0] for p in self.arrow) - min(p[0] for p in self.arrow)
        height = max(p[1] for p in self.arrow) - min(p[1] for p in self.arrow)
        return max(width, height)


def path_vertices(definition: str) -> list[Point]:
    """Endpoints of an SVG path, skipping the radii and flags an arc command carries.

    Pairing every number in the definition treats ``A``'s seven parameters as coordinates and
    invents vertices far outside the canvas, which is exactly the kind of false reading that
    made an earlier audit distrust its own output.
    """
    tokens = re.findall(r"([MLACQZmlacqz])|(-?\d+\.?\d*)", definition)
    commands: list[tuple[str, list[float]]] = []
    current: str | None = None
    numbers: list[float] = []
    for command, number in tokens:
        if command:
            if current:
                commands.append((current, numbers))
            current, numbers = command.upper(), []
        elif number:
            numbers.append(float(number))
    if current:
        commands.append((current, numbers))
    stride = {"M": (2, 0), "L": (2, 0), "A": (7, 5), "C": (6, 4), "Q": (4, 2)}
    vertices: list[Point] = []
    for command, values in commands:
        if command not in stride:
            continue
        step, offset = stride[command]
        for index in range(0, len(values) - step + 1, step):
            vertices.append((int(values[index + offset]), int(values[index + offset + 1])))
    return vertices


def node_boxes(scene: Any) -> dict[str, LayoutBox]:
    """Every node box in the scene, whichever primitive its family used to draw it.

    Six families emit ``SceneNode``; the rest wrap a rect or a circle in a group. Reading only
    ``scene.nodes`` silently skipped seventeen kinds, so every node-related check passed by
    having nothing to compare against.
    """
    from ..scene import SceneCircle, SceneGroup, SceneRect

    boxes: dict[str, LayoutBox] = {}
    for node in scene.nodes:
        boxes[node.id] = LayoutBox(node.box.x, node.box.y, node.box.w, node.box.h)

    def walk(items: Iterable[Any], group_id: str | None = None) -> None:
        for item in items or ():
            if isinstance(item, SceneGroup):
                walk(item.children, item.id)
                continue
            if not group_id or is_connector(group_id) or is_guide(group_id):
                continue
            key = group_id.split(":", 1)[-1] if ":" in group_id else group_id
            if key in boxes:
                continue
            if isinstance(item, SceneRect):
                boxes[key] = LayoutBox(item.box.x, item.box.y, item.box.w, item.box.h)
            elif isinstance(item, SceneCircle):
                boxes[key] = LayoutBox(item.cx - item.r, item.cy - item.r, 2 * item.r, 2 * item.r)

    walk(scene.primitives)
    return boxes


def collect_connectors(scene: Any) -> list[Connector]:
    """Connectors from both representations, with endpoints inferred where absent."""
    from ..scene import SceneGroup, SceneLine, ScenePath, ScenePolyline

    boxes = node_boxes(scene)
    connectors: list[Connector] = []
    for edge in scene.edges:
        connectors.append(Connector(
            edge.id,
            tuple(tuple(point) for point in edge.points),
            edge.source,
            edge.target,
            tuple(tuple(point) for point in edge.arrow.points) if edge.arrow else None,
        ))

    def walk(items: Iterable[Any]) -> None:
        for item in items or ():
            item_id = getattr(item, "id", "") or ""
            if isinstance(item, SceneGroup):
                walk(item.children)
                continue
            if is_guide(item_id) or is_marker(item_id) or not is_connector(item_id):
                continue
            if isinstance(item, ScenePolyline):
                points = [tuple(point) for point in item.points]
                curved = False
            elif isinstance(item, SceneLine):
                points = [tuple(item.start), tuple(item.end)]
                curved = False
            elif isinstance(item, ScenePath):
                points = path_vertices(item.d)
                curved = True
            else:
                continue
            if len(points) >= 2:
                source, target = infer_endpoints(points, boxes)
                connectors.append(Connector(item_id, tuple(points), source, target, None, curved))

    walk(scene.primitives)
    return connectors


def infer_endpoints(points: list[Point], boxes: dict[str, LayoutBox]) -> tuple[str | None, str | None]:
    """Which nodes a loose primitive connects, judged by where it starts and ends."""
    def at(point: Point) -> str | None:
        for node_id, box in boxes.items():
            if box.x - 3 <= point[0] <= box.x + box.w + 3 and box.y - 3 <= point[1] <= box.y + box.h + 3:
                return node_id
        return None

    return at(points[0]), at(points[-1])


def blocks_lane(box: LayoutBox, lane: int, span: tuple[int, int], *, horizontal: bool) -> bool:
    """True when a run at ``lane`` would touch this box, border included.

    Border contact counts because a run sitting exactly on a node's edge merges with its
    outline; the interior-only test that shipped first read that as clearance.
    """
    low, high = sorted(span)
    if horizontal:
        return box.y <= lane <= box.y + box.h and low < box.x + box.w and high > box.x
    return box.x <= lane <= box.x + box.w and low < box.y + box.h and high > box.y


def run_hits_segment(lane: int, span: tuple[int, int], segment: Segment, *, horizontal: bool) -> bool:
    """True when a run at ``lane`` would touch an already placed segment."""
    low, high = sorted(span)
    (ax, ay), (bx, by) = segment
    if horizontal:
        if ay == by:
            return ay == lane and min(max(ax, bx), high) > max(min(ax, bx), low)
        return low <= ax <= high and min(ay, by) <= lane <= max(ay, by)
    if ax == bx:
        return ax == lane and min(max(ay, by), high) > max(min(ay, by), low)
    return low <= ay <= high and min(ax, bx) <= lane <= max(ax, bx)


def route_is_clear(points: list[Point], obstacles: list[LayoutBox], placed: list[Segment]) -> bool:
    """True when every run in a candidate route clears the nodes and the earlier connectors.

    Whole-route rather than lane-only: moving a lane changes the length of the stubs that drop
    from the source and rise into the target, and those stubs are what collide.
    """
    for first, second in zip(points, points[1:]):
        if first == second:
            continue
        horizontal = first[1] == second[1]
        lane = first[1] if horizontal else first[0]
        span = (first[0], second[0]) if horizontal else (first[1], second[1])
        if any(blocks_lane(box, lane, span, horizontal=horizontal) for box in obstacles):
            return False
        if any(run_hits_segment(lane, span, segment, horizontal=horizontal) for segment in placed):
            return False
    return True


def meeting_point(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    """Where an axis-aligned pair meets, endpoints included, or ``None``."""
    if a[0] == b[0] and c[1] == d[1]:
        x, y = a[0], c[1]
        if min(c[0], d[0]) <= x <= max(c[0], d[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
            return (x, y)
    if a[1] == b[1] and c[0] == d[0]:
        x, y = c[0], a[1]
        if min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(c[1], d[1]) <= y <= max(c[1], d[1]):
            return (x, y)
    return None


def shares_run(first: Connector, second: Connector) -> bool:
    """True when two connectors deliberately overlap, as tree siblings do on a shared trunk.

    A bracket-style hierarchy draws one vertical drop and one horizontal bar for the whole
    sibling set, so those connectors are collinear on purpose and must not be read as tangled.
    """
    for a1, a2 in first.segments:
        for b1, b2 in second.segments:
            if a1[0] == a2[0] == b1[0] == b2[0]:
                if min(max(a1[1], a2[1]), max(b1[1], b2[1])) > max(min(a1[1], a2[1]), min(b1[1], b2[1])):
                    return True
            if a1[1] == a2[1] == b1[1] == b2[1]:
                if min(max(a1[0], a2[0]), max(b1[0], b2[0])) > max(min(a1[0], a2[0]), min(b1[0], b2[0])):
                    return True
    return False


def graze_overlap(segment: Segment, box: LayoutBox, contract: ConnectorContract = DEFAULT_CONTRACT) -> int:
    """How far a run travels along one of the box's own borders, past the tolerance."""
    (ax, ay), (bx, by) = segment
    right, bottom = box.x + box.w, box.y + box.h
    if ay == by and ay in {box.y, bottom}:
        low, high = sorted((ax, bx))
        overlap = min(high, right) - max(low, box.x)
    elif ax == bx and ax in {box.x, right}:
        low, high = sorted((ay, by))
        overlap = min(high, bottom) - max(low, box.y)
    else:
        return 0
    return overlap if overlap >= contract.graze_tolerance else 0


def assign_bridges(scene_edges: list[Any]) -> list[Any]:
    """Mark hop-over points on the later edge of every crossing routing could not avoid.

    Routing dodges what it can, but a congested corridor can leave a real crossing: two
    connectors may both need the single clear band between two node rows. A hop-over states
    which one passes over instead of leaving an ambiguous junction.
    """
    bridge_map: dict[str, list[Point]] = defaultdict(list)
    for index, upper in enumerate(scene_edges):
        for lower in scene_edges[index + 1:]:
            if {upper.source, upper.target} & {lower.source, lower.target}:
                continue
            crossing = _first_interior_crossing(upper.points, lower.points)
            if crossing:
                bridge_map[lower.id].append(crossing)
    return [replace(edge, bridges=tuple(sorted(set(bridge_map[edge.id])))) for edge in scene_edges]


def _first_interior_crossing(left: tuple[Point, ...], right: tuple[Point, ...]) -> Point | None:
    """Strictly interior only: a hop-over needs clearance on both sides to render."""
    for a, b in zip(left, left[1:]):
        for c, d in zip(right, right[1:]):
            if a[0] == b[0] and c[1] == d[1]:
                if min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1]):
                    return (a[0], c[1])
            elif a[1] == b[1] and c[0] == d[0]:
                if min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1]):
                    return (c[0], a[1])
    return None


def approach_needs_rerouting(
    start: Point, end: Point, contract: ConnectorContract = DEFAULT_CONTRACT
) -> bool:
    """True when the gap between two faces is too thin to land an arrowhead in.

    Two nodes can sit only a few units apart on one axis while being far apart on the other.
    Routing into the near face then leaves an approach shorter than the arrowhead, which draws
    as a kink at the corner rather than an arrow.
    """
    return abs(end[0] - start[0]) <= contract.elbow_radius and abs(end[1] - start[1]) <= contract.elbow_radius


def perpendicular_approach(
    start: Point,
    target: LayoutBox,
    contract: ConnectorContract = DEFAULT_CONTRACT,
) -> tuple[Point, Point] | None:
    """Re-enter a target through the face that has room, given where the run comes from.

    Returns the ``(corner, entry)`` pair to append, or ``None`` when neither perpendicular face
    offers more clearance than the one already chosen.
    """
    centre_x = target.x + target.w // 2
    if start[1] <= target.y - contract.elbow_radius:
        return (centre_x, start[1]), (centre_x, target.y)
    if start[1] >= target.y + target.h + contract.elbow_radius:
        return (centre_x, start[1]), (centre_x, target.y + target.h)
    return None


def check_contract(scene: Any, contract: ConnectorContract = DEFAULT_CONTRACT) -> list[Any]:
    """Connector diagnostics for any family, reported against one shared set of rules.

    Called from the single finalize step every diagram kind passes through, so a family cannot
    be added without inheriting the gate.
    """
    from ..validation.models import DrawingDiagnostic

    diagnostics: list[Any] = []
    boxes = node_boxes(scene)
    connectors = collect_connectors(scene)
    bridged = {point for edge in scene.edges for point in edge.bridges}

    for connector in connectors:
        for node_id, box in boxes.items():
            if node_id in {connector.source, connector.target}:
                continue
            for segment in connector.segments:
                overlap = graze_overlap(segment, box, contract)
                if overlap:
                    diagnostics.append(DrawingDiagnostic(
                        "TASTE", "DG136",
                        f"connector runs {overlap} units along the border of unrelated node {node_id}",
                        connector.id,
                        hint="route the connector clear of the node instead of along its outline",
                    ))
                    break

    for index, first in enumerate(connectors):
        for second in connectors[index + 1:]:
            if shares_run(first, second):
                continue
            exempt = {first.points[0], first.points[-1]} & {second.points[0], second.points[-1]}
            crossing = None
            for a1, a2 in first.segments:
                for b1, b2 in second.segments:
                    point = meeting_point(a1, a2, b1, b2)
                    if point and point not in exempt and point not in bridged:
                        crossing = point
                        break
                if crossing:
                    break
            if crossing:
                diagnostics.append(DrawingDiagnostic(
                    "TASTE", "DG204",
                    f"connectors {first.id} and {second.id} cross at {crossing} without a hop",
                    first.id,
                    hint="reroute one connector or let it hop over the other",
                ))

    for connector in connectors:
        extent = connector.arrow_extent
        if extent and connector.final_run <= extent:
            diagnostics.append(DrawingDiagnostic(
                "TASTE", "DG137",
                f"final run is {connector.final_run} units but the arrowhead needs more than {extent}",
                connector.id,
                hint="lengthen the approach so the arrowhead reads as an arrow, not a kink",
            ))

    return diagnostics
