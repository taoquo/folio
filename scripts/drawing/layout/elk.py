from __future__ import annotations

import json
import shutil
import subprocess
from collections import defaultdict
from dataclasses import replace
from math import cos, pi, sin
from pathlib import Path
from typing import Any

from ..connectors import route_orthogonal
from ..connectors.labels import LABEL_REACH, compact_edge_label, place_edge_labels
from ..grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR, ArchitectureGrammar
from ..legend import legend_band
from ..models import DrawingPlan, VisualEdgePlan
from ..semantics.models import SemanticDiagram
from ..stage import current as current_stage
from ..validation.layout import validate_layout
from .constraints import compile_layout_constraints, row_gap_requirements
from .models import LayoutBox, LayoutConstraintSet, LayoutEdge, LayoutResult, PortPreference
from .regions import region_frames, region_label_bands

ROOT = Path(__file__).resolve().parents[3]
ELK_RUNNER = ROOT / "scripts" / "diagram_elk_runner.js"
ELK_BUNDLED = ROOT / "scripts" / "vendor" / "elk.bundled.js"
GRID = 4
FAN_GAP = 12
# A connector has to enter its face with an arrowhead's depth of straight run,
# or the tip lands on the corner it turned at and reads as a kink. The
# arrowhead is type, so this floor does not scale with the stage.
ARROW_APPROACH = DEFAULT_ARCHITECTURE_GRAMMAR.geometry.arrow_size * 2
# The least air between two rows on a composed stage. It is a floor, not a
# value: the pitch is computed from the frame, and this only stops a scaled
# stage from placing one row on top of the next -- and leaves room for the band
# header that replaces the left gutter there. The default stage keeps its own
# measured pitch untouched.
_MIN_ROW_CLEARANCE = 16


def _row_clearance() -> int:
    return 0 if current_stage().is_default else _MIN_ROW_CLEARANCE


def _fitted_gaps(needs: list[int], space: int, floor: int) -> list[int]:
    """Per-pair gaps that fit the row, keeping a labelled pair wider.

    A labelled pair's gap is a requirement, but a row that cannot hold its
    requirements still has to be drawn. The shortfall is taken from every gap
    above ``floor`` in proportion to how far above it sits, so a labelled pair
    keeps its advantage over an unlabelled one instead of one gap absorbing the
    whole deficit and the label landing on a box.

    A row with one size of gap takes exactly the uniform gap it always did:
    the proportional form reduces to that when every requirement is equal.

    Every gap stays on the 4-unit grid. The row positions are cumulative, so a
    gap that is not a grid multiple puts every box after it off the grid too,
    and the plate then fails its own geometry contract (DG121) for a defect the
    reader never sees. Rounding down keeps the row inside the space it was
    given.
    """
    def grid(value: int) -> int:
        return value // GRID * GRID

    gaps = list(needs)
    if not gaps or sum(gaps) <= space:
        return gaps
    if len(set(gaps)) == 1:
        return [min(gaps[0], max(floor, grid(space // len(gaps))))] * len(gaps)
    excess = sum(gap - floor for gap in gaps)
    room = max(0, space - floor * len(gaps))
    if excess <= 0:
        return gaps
    factor = room / excess
    return [max(floor, grid(floor + int((gap - floor) * factor))) for gap in gaps]



def layout_drawing(
    drawing: DrawingPlan,
    semantic: SemanticDiagram | None = None,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> LayoutResult:
    """Lay out a DrawingPlan without converting it back to the legacy diagram spec."""
    del semantic  # Semantics have already been resolved into DrawingPlan constraints.
    constraints = compile_layout_constraints(drawing, grammar)
    _require_elk()
    seed_boxes = _elk_seed_layout(drawing, constraints)
    boxes = _compose(drawing, constraints, seed_boxes, grammar)
    # The group boundaries are known once the rows are, and they are geometry
    # the render pass will draw, so the label placer is told about them here --
    # both the frames it must not cross and the strip inside each frame where
    # the boundary's own name is set.
    frames = region_frames(drawing, boxes, grammar)
    edges = _route_edges(
        drawing,
        constraints,
        boxes,
        tuple(box for _region, box in frames),
        region_label_bands(frames, grammar),
    )
    bounds = _bounds_for(boxes, edges)
    result = LayoutResult(boxes=boxes, edges=edges, bounds=bounds)
    issues = validate_layout(result, drawing.width, drawing.height)
    if issues:
        result = LayoutResult(boxes=boxes, edges=edges, bounds=bounds, warnings=issues)
    return result


def _require_elk() -> None:
    if not elk_available():
        raise RuntimeError("ELK layout unavailable: require node and scripts/vendor/elk.bundled.js")


def elk_available() -> bool:
    """Return True when the bundled ELK runner can be executed by node."""
    return shutil.which("node") is not None and ELK_RUNNER.exists() and ELK_BUNDLED.exists()


def _elk_seed_layout(drawing: DrawingPlan, constraints: LayoutConstraintSet) -> dict[str, LayoutBox]:
    """Ask ELK for topology-aware ordering; Folio composition then snaps it to its grammar."""
    direction = "RIGHT" if constraints.axis == "left-right" else "DOWN"
    ordered_ids = _ordered_node_ids(drawing, constraints)
    graph: dict[str, Any] = {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": direction,
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
            "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
            "elk.layered.spacing.nodeNodeBetweenLayers": str(constraints.layer_gap),
            "elk.spacing.nodeNode": str(constraints.node_gap),
            "elk.spacing.edgeNode": str(constraints.edge_node_gap),
            "elk.spacing.edgeEdge": str(constraints.edge_edge_gap),
            "elk.padding": "[top=80,left=96,bottom=72,right=96]",
        },
        "children": [
            {
                "id": node_id,
                "width": constraints.node_sizes[node_id][0],
                "height": constraints.node_sizes[node_id][1],
            }
            for node_id in ordered_ids
        ],
        "edges": [
            {
                "id": edge.id,
                "sources": [edge.source],
                "targets": [edge.target],
                "layoutOptions": {
                    "elk.layered.priority.straightness": "20"
                    if (edge.source, edge.target) in constraints.preferred_adjacency
                    else "1"
                },
            }
            for edge in drawing.edges
        ],
    }
    result = subprocess.run(
        ["node", str(ELK_RUNNER)],
        input=json.dumps(graph),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "elk runner failed")
    raw = json.loads(result.stdout)
    return {
        item["id"]: LayoutBox(
            _grid(item.get("x", 0)),
            _grid(item.get("y", 0)),
            _grid(item.get("width", constraints.node_sizes[item["id"]][0])),
            _grid(item.get("height", constraints.node_sizes[item["id"]][1])),
        )
        for item in raw.get("children", [])
    }


def _ordered_node_ids(drawing: DrawingPlan, constraints: LayoutConstraintSet) -> list[str]:
    known = {node.id for node in drawing.nodes}
    ordered: list[str] = []

    def add(node_id: str) -> None:
        if node_id in known and node_id not in ordered:
            ordered.append(node_id)

    for node_id in constraints.spine:
        add(node_id)
        for sidecar in constraints.sidecars.get(node_id, ()):
            add(sidecar)
    for layer_id in constraints.layer_order:
        for node_id in constraints.node_order.get(layer_id, ()):
            add(node_id)
    for node in drawing.nodes:
        add(node.id)
    return ordered


def _compose(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> dict[str, LayoutBox]:
    if drawing.composition.pattern == "pipeline":
        return _pipeline_boxes(drawing, constraints, seed, grammar)
    if drawing.composition.pattern == "hub":
        return _hub_boxes(drawing, constraints, seed)
    return _layered_boxes(drawing, constraints, seed, grammar)


# The legend is drawn in the bottom chrome band. A region pads its members and
# can push its border down into that band, so the last row moves up by exactly
# the overlap. Nodes alone already stop above the legend.
LEGEND_TOP_FROM_BOTTOM = 60
LEGEND_CLEARANCE = 8


def _region_wraps_last_row(drawing: DrawingPlan, last_row: list[str]) -> bool:
    members = set(last_row)
    return any(
        region.treatment in {"soft-boundary", "trust-boundary", "phase-band"} and members & set(region.members)
        for region in drawing.regions
    )


# The least margin a composed stage keeps at the edge of the canvas. A frame is
# the first thing to give way when a row needs the room: losing four units of
# margin is a smaller failure than splitting a reading group across rows.
_MIN_FRAME_EDGE = 8


def _widen_frame(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    left: int,
    right: int,
    groups: list[list[str]],
    minimum_gap: int = 16,
) -> tuple[int, int]:
    """Give margin back to a row that cannot sit inside the frame as authored.

    What the row is measured against depends on what the frame is. On the
    authored stage the frame is part of the composition -- the left column is
    the band-name gutter -- so it gives way only to prevent a split, and the
    question is asked at ``minimum_gap``, exactly as ``_row_chunks`` asks it.

    A composed stage computes its frame, and its margins are margin. There the
    row is measured at the gaps it will actually be placed with, labels
    reserved: giving back only enough to keep the row whole and not enough to
    keep its words has solved nothing.
    """
    base = minimum_gap if current_stage().is_default else None
    widest = max(
        (sum(constraints.node_sizes[node_id][0] for node_id in group)
         + sum(row_gap_requirements(group, drawing.edges, constraints, base))
         for group in groups if group),
        default=0,
    )
    shortfall = widest - (right - left)
    if shortfall <= 0:
        return left, right
    slack = min(left - _MIN_FRAME_EDGE,
                drawing.width - _MIN_FRAME_EDGE - right,
                -(-shortfall // 2))
    return left - slack, right + slack


def _row_chunks(
    members: list[str],
    constraints: LayoutConstraintSet,
    available: int,
    edges: tuple[VisualEdgePlan, ...] | list[VisualEdgePlan],
    minimum_gap: int = 16,
) -> list[list[str]]:
    """Split one layer across rows when its boxes cannot sit side by side.

    A layer is a reading group, not a promise that its members share a row. On a
    narrow stage the same group is wider than the frame, and packing it tighter
    is not available: below `minimum_gap` the boxes touch. Splitting it into the
    fewest balanced rows is what keeps the drawing composable at all -- and at
    the default stage nothing is wider than the frame, so this returns one row
    and no published drawing moves.
    """

    def fits(chunk: list[str]) -> bool:
        widths = sum(constraints.node_sizes[node_id][0] for node_id in chunk)
        return widths + sum(row_gap_requirements(
            chunk, edges, constraints, minimum_gap,
            reserve_labels=False)) <= available

    if len(members) <= 1 or fits(members):
        return [members]
    for count in range(2, len(members) + 1):
        size = -(-len(members) // count)
        chunks = [members[index:index + size] for index in range(0, len(members), size)]
        if all(fits(chunk) for chunk in chunks):
            return chunks
    return [members]


def _layered_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> dict[str, LayoutBox]:
    geometry = grammar.geometry
    top, bottom = geometry.frame_top, drawing.height - geometry.frame_bottom
    left, right = geometry.frame_left, drawing.width - geometry.frame_right
    groups: list[tuple[str, list[str]]] = []
    assigned: set[str] = set()
    for layer_id in constraints.layer_order:
        members = [node_id for node_id in constraints.node_order.get(layer_id, ()) if node_id in seed]
        if members:
            groups.append((layer_id, members))
            assigned.update(members)
    remainder = [node.id for node in drawing.nodes if node.id not in assigned]
    if remainder:
        groups.append(("unlayered", remainder))
    # A reading group is one row on the default stage. On a narrower one the
    # frame gives way before the group does, so the widening is measured on the
    # groups as authored, not on the chunks they might become.
    left, right = _widen_frame(drawing, constraints, left, right, [members for _layer, members in groups])
    rows: list[tuple[str, list[str]]] = []
    for layer_id, members in groups:
        rows.extend((layer_id, chunk) for chunk in _row_chunks(
            members, constraints, right - left, drawing.edges))
    if not rows:
        rows = [("default", [node.id for node in drawing.nodes])]

    if drawing.legend:
        legend_top = drawing.height - LEGEND_TOP_FROM_BOTTOM
        if current_stage().is_default:
            if _region_wraps_last_row(drawing, rows[-1][1]):
                region_bottom = bottom + geometry.group_pad_bottom
                bottom -= max(0, region_bottom - (legend_top - LEGEND_CLEARANCE))
        else:
            # The frame bottom scales with the stage, so on a composed plate it
            # no longer clears the legend, which stays anchored to the canvas.
            # Ask the legend module for the box it will actually draw: a legend
            # whose items wrapped is taller than the constant the authored
            # stage reserved.
            band = legend_band(drawing)
            if band is not None:
                bottom = min(bottom, band.top(drawing.height) - LEGEND_CLEARANCE)
    # The last row's own height is what the rows have to stay above, and it is
    # a node height, so it scales with the stage like everything else.
    tallest = max((constraints.node_sizes[node_id][1] for _layer, row in rows for node_id in row), default=64)
    if len(rows) == 1:
        row_step = 0
    else:
        spread = (bottom - top - tallest) / (len(rows) - 1)
        if current_stage().is_default:
            row_step = spread
        else:
            # A composed stage packs its rows instead of spreading them over the
            # authored canvas height. The plate is cropped to its ink, so slack
            # left at the bottom is slack the reader never sees; spreading two
            # rows across 500 units only pushes them apart into a drawing that
            # reads as two islands.
            row_step = min(spread, tallest + max(geometry.layer_gap, _MIN_ROW_CLEARANCE))
    # A row pitch below the node height is an overlap, not a composition. The
    # rows then run past the frame and the layout says so, which is the answer:
    # the stage is too short for this many rows.
    row_step = max(row_step, tallest + _row_clearance())
    boxes: dict[str, LayoutBox] = {}
    for row_index, (_layer, members) in enumerate(rows):
        requested = list(members)
        requested_rank = {node_id: index for index, node_id in enumerate(requested)}
        ordered = sorted(
            members,
            key=lambda node_id: (
                requested_rank.get(node_id, 10_000),
                seed.get(node_id, LayoutBox(0, 0, 0, 0)).x,
                node_id,
            ),
        )
        widths = [constraints.node_sizes[node_id][0] for node_id in ordered]
        available = right - left
        gaps = _fitted_gaps(
            row_gap_requirements(ordered, drawing.edges, constraints),
            available - sum(widths), floor=16)
        total = sum(widths) + sum(gaps)
        x = _grid(left + max(0, (available - total) / 2))
        y = _grid(top + row_index * row_step)
        for index, (node_id, node_w) in enumerate(zip(ordered, widths)):
            node_h = constraints.node_sizes[node_id][1]
            boxes[node_id] = LayoutBox(x, y, node_w, node_h)
            x = _grid(x + node_w + (gaps[index] if index < len(gaps) else 0))
    return _align_secondary_rows(drawing, boxes, left, right)


def _align_secondary_rows(
    drawing: DrawingPlan,
    boxes: dict[str, LayoutBox],
    left: int,
    right: int,
) -> dict[str, LayoutBox]:
    result = dict(boxes)
    regions = {node.id: node.region for node in drawing.nodes}
    members: dict[str | None, list[str]] = defaultdict(list)
    for node in drawing.nodes:
        members[node.region].append(node.id)
    spine_pairs = set(zip(drawing.composition.spine, drawing.composition.spine[1:]))
    for edge in drawing.edges:
        if (edge.source, edge.target) in spine_pairs or regions.get(edge.source) == regions.get(edge.target):
            continue
        source_region = regions.get(edge.source)
        target_region = regions.get(edge.target)
        source_members = members[source_region]
        target_members = members[target_region]
        movable_region = source_region if len(source_members) <= len(target_members) else target_region
        movable_id = edge.source if movable_region == source_region else edge.target
        fixed_id = edge.target if movable_id == edge.source else edge.source
        dx = result[fixed_id].x - result[movable_id].x
        shifted = [
            LayoutBox(result[node_id].x + dx, result[node_id].y, result[node_id].w, result[node_id].h)
            for node_id in members[movable_region]
        ]
        if shifted and min(box.x for box in shifted) >= left and max(box.x + box.w for box in shifted) <= right:
            for node_id, box in zip(members[movable_region], shifted):
                result[node_id] = box
    return result


def _bands_follow_flow(bands, flow: list[str]) -> bool:
    """True when the layer bands are consecutive runs of the declaration order.

    A band groups members that sit next to each other. If the bands interleave
    -- `a, b, a` -- they describe one structure seen from two angles, not rows,
    and forcing them into rows would draw a band across rows it does not own.
    The spine is not consulted here: it orders the reading, and banding still
    decides which row a node belongs to.
    """
    seen: list[str] = []
    for band in bands:
        run = [node_id for node_id in flow if node_id in set(band.members)]
        if not run:
            continue
        positions = [flow.index(node_id) for node_id in run]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            return False
        seen.extend(run)
    return seen == [node_id for node_id in flow if node_id in set(seen)]


def _pipeline_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> dict[str, LayoutBox]:
    geometry = grammar.geometry
    ordered = list(constraints.spine) or _ordered_node_ids(drawing, constraints)
    ordered = [node_id for node_id in ordered if node_id in seed]
    remainder = [node_id for node_id in _ordered_node_ids(drawing, constraints) if node_id not in ordered]
    left, right = geometry.pipeline_frame_left, drawing.width - geometry.pipeline_frame_right
    boxes: dict[str, LayoutBox] = {}
    pipeline_nodes = [*ordered, *remainder]
    # A pipeline that declares layers has already said which nodes belong on
    # which row. Chunking by four instead leaves the layer bands drawn around
    # nodes that are no longer in them, so the declared layers win -- but only
    # when each band is a run of the flow order. A band that interleaves with
    # another is a stack, not a pipeline row, and forcing it into rows would
    # break the order the spine states.
    bands = [region for region in drawing.regions if region.treatment == "layer-band"]
    declared = [node.id for node in drawing.nodes]
    if bands and not _bands_follow_flow(bands, declared):
        bands = []
    # A band is a row until its members cannot sit side by side in the frame;
    # then it splits into balanced rows, exactly as the layered composition
    # does. At the default stage nothing splits and the drawing is unchanged.
    groups = (
        [[node_id for node_id in band.members if node_id in seed] for band in bands]
        if bands
        else [pipeline_nodes[index:index + 4] for index in range(0, len(pipeline_nodes), 4)]
    )
    if bands:
        grouped = {node_id for group in groups for node_id in group}
        leftovers = [node_id for node_id in pipeline_nodes if node_id not in grouped]
        if leftovers:
            groups.append(leftovers)
    # As in the layered composition, margin is the first thing to give way: a
    # row that would otherwise split gets the frame's slack down to 8 units.
    left, right = _widen_frame(drawing, constraints, left, right, groups, minimum_gap=12)
    available = right - left
    chunks = [
        chunk
        for group in groups
        for chunk in _row_chunks(group, constraints, available, drawing.edges, minimum_gap=12)
    ]
    chunks = [chunk for chunk in chunks if chunk] or [[]]
    tallest = max((constraints.node_sizes[node_id][1] for node_id in pipeline_nodes), default=64)
    if bands:
        # One row per declared layer, fitted inside the canvas: a fixed 148px
        # step would push the last layer band past the bottom edge as soon as
        # the payload declares three layers.
        top, bottom = geometry.frame_top, drawing.height - geometry.frame_bottom
        step = geometry.pipeline_step if len(chunks) < 2 else min(
            geometry.pipeline_step, (bottom - top - tallest) / (len(chunks) - 1))
        step = max(step, tallest + _row_clearance())
        if current_stage().is_default:
            # The authored canvas centers its rows in the frame; that spacing is
            # part of every published figure.
            first_y = _grid(top + max(0, (bottom - top - tallest - step * (len(chunks) - 1)) / 2))
        else:
            # A composed stage packs from the frame top. Centering a two-row
            # pipeline in the frame leaves a hole under the title that the ink
            # crop cannot remove -- the title's box spans it -- so the plate
            # reads as a title, a void, then a drawing. Bottom slack is cropped
            # away; top slack is not.
            first_y = _grid(top)
    else:
        step = max(geometry.pipeline_step, tallest + _row_clearance())
        first_y = _grid(drawing.height * (0.34 if len(chunks) > 1 else 0.42))
    for row_index, chunk in enumerate(chunks):
        widths = [constraints.node_sizes[node_id][0] for node_id in chunk]
        gaps = _fitted_gaps(
            row_gap_requirements(chunk, drawing.edges, constraints),
            right - left - sum(widths), floor=12)
        total = sum(widths) + sum(gaps)
        x = _grid(left + max(0, (right - left - total) / 2))
        y = _grid(first_y + row_index * step)
        # A serpentine pipeline reverses alternate rows to keep the next arrow
        # short. A layer band is not serpentine: its members are stated in flow
        # order, and reversing them turns the arrows backwards.
        row = chunk if bands or row_index % 2 == 0 else list(reversed(chunk))
        # The gap belongs to the pair, and a reversed row reads the same pairs
        # in the other direction, so the requirements reverse with it.
        row_gaps = gaps if row is chunk else list(reversed(gaps))
        for index, node_id in enumerate(row):
            w, h = constraints.node_sizes[node_id]
            boxes[node_id] = LayoutBox(x, y, w, h)
            x = _grid(x + w + (row_gaps[index] if index < len(row_gaps) else 0))

    return boxes


def _hub_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
) -> dict[str, LayoutBox]:
    focus = drawing.hierarchy.focus_node or (constraints.spine[0] if constraints.spine else None)
    if focus not in seed:
        focus = _ordered_node_ids(drawing, constraints)[0]
    focus_w, focus_h = constraints.node_sizes[focus]
    center_x = _grid(drawing.width / 2)
    if drawing.legend:
        # The ring sits above the legend band, so the lowest satellite clears
        # the legend box without shrinking the horizontal spread.
        center_y = _grid(drawing.height / 2 - 8)
        radius_y = min(168, max(132, drawing.height // 3 - 8))
    else:
        center_y = _grid(drawing.height / 2 + 16)
        radius_y = min(176, max(132, drawing.height // 3))
    boxes = {focus: LayoutBox(_grid(center_x - focus_w / 2), _grid(center_y - focus_h / 2), focus_w, focus_h)}
    satellites = [node_id for node_id in _ordered_node_ids(drawing, constraints) if node_id != focus]
    radius_x = min(320, max(220, drawing.width // 3))
    for index, node_id in enumerate(satellites):
        angle = -pi / 2 + (2 * pi * index / max(1, len(satellites)))
        w, h = constraints.node_sizes[node_id]
        x = _grid(center_x + radius_x * cos(angle) - w / 2)
        y = _grid(center_y + radius_y * sin(angle) - h / 2)
        boxes[node_id] = LayoutBox(x, y, w, h)
    return boxes


def _route_edges(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    boxes: dict[str, LayoutBox],
    boundaries: tuple[LayoutBox, ...] = (),
    reserved: tuple[LayoutBox, ...] = (),
) -> list[LayoutEdge]:
    preferences = {
        edge.id: _spatial_preference(
            edge,
            constraints.port_preferences[edge.id],
            boxes,
            preserve_layers=drawing.composition.pattern == "layered",
        )
        for edge in drawing.edges
    }
    incidents: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for edge in drawing.edges:
        preference = preferences[edge.id]
        incidents[(edge.source, preference.source)].append((edge.id, "source"))
        incidents[(edge.target, preference.target)].append((edge.id, "target"))
    vertical_edges = [
        edge.id
        for edge in drawing.edges
        if preferences[edge.id].source in {"top", "bottom"}
        and preferences[edge.id].target in {"top", "bottom"}
    ]
    lane_offsets = {
        edge_id: _grid((index - (len(vertical_edges) - 1) / 2) * FAN_GAP)
        for index, edge_id in enumerate(vertical_edges)
    }
    anchors: dict[tuple[str, str], tuple[int, int]] = {}
    for (node_id, side), entries in incidents.items():
        for index, (edge_id, endpoint) in enumerate(sorted(entries)):
            anchors[(edge_id, endpoint)] = _fan_anchor(boxes[node_id], side, index, len(entries))

    results: list[LayoutEdge] = []
    for edge in drawing.edges:
        start = anchors[(edge.id, "source")]
        end = anchors[(edge.id, "target")]
        preference = preferences[edge.id]
        start_stub = _outward_stub(start, preference.source, constraints.edge_node_gap // 2)
        end_stub = _outward_stub(end, preference.target, constraints.edge_node_gap // 2)
        middle = _preferred_middle_route(start_stub, end_stub, preference, lane_offsets.get(edge.id, 0))
        if _route_crosses_nodes(middle, boxes, {edge.source, edge.target}):
            middle = route_orthogonal(
                start_stub,
                end_stub,
                boxes,
                set(),
                drawing.width,
                drawing.height,
                clearance=constraints.edge_node_gap,
            )
        points = _simplify_points([start, *middle, end])
        points = _off_boundaries(points, boundaries, max(4, constraints.edge_edge_gap))
        label = compact_edge_label(edge.label)
        results.append(LayoutEdge(edge.source, edge.target, points, label, None, edge.id))
    placed = place_edge_labels(
        results,
        list(boxes.values()),
        drawing.width,
        drawing.height,
        obstacles=reserved,
        boundaries=boundaries,
        # A label names the line it sits beside, on every stage. The authored
        # canvas used to let one drift as far as 72 units to find a free slot,
        # which reads as a word belonging to nothing. The rule is the distance,
        # not the stage: a label that cannot stay with its connector is dropped.
        reach=LABEL_REACH,
    )
    # A connector label is an annotation on one path, not a field every path
    # carries: naming one transition and leaving another unnamed is how
    # diagrams are read. So a label that cannot sit beside its own line is
    # dropped on its own, unlike a node descriptor or a band header, where one
    # missing instance would read as a fault.
    return [edge if edge.label_box else replace(edge, label=None) for edge in placed]


def _off_boundaries(
    points: list[tuple[int, int]],
    boundaries: tuple[LayoutBox, ...],
    clearance: int,
) -> list[tuple[int, int]]:
    """Move a connector run that would be drawn along a group boundary.

    A route crosses a boundary; it does not travel on one. When the round-trip
    midpoint of a row gap lands on the boundary's own edge -- which happens as
    soon as the gap and the padding are the same size -- the two lines are drawn
    on top of each other and the dashed border reads as solid. The run steps
    outside the group it is entering, which is the side a crossing comes from.
    """
    if current_stage().is_default or not boundaries:
        return points
    result = list(points)
    for frame in boundaries:
        for edge_y, direction in ((frame.y, -1), (frame.y + frame.h, 1)):
            moved: list[int] = []
            for index in range(len(result) - 1):
                (x0, y0), (x1, y1) = result[index], result[index + 1]
                if y0 != edge_y or y1 != edge_y:
                    continue
                if min(x0, x1) >= frame.x + frame.w or max(x0, x1) <= frame.x:
                    continue
                moved.extend((index, index + 1))
            for index in dict.fromkeys(moved):
                x, y = result[index]
                result[index] = (x, y + direction * clearance)
    return result


def _outward_stub(point: tuple[int, int], side: str, distance: int) -> tuple[int, int]:
    x, y = point
    return {
        "top": (x, y - distance),
        "right": (x + distance, y),
        "bottom": (x, y + distance),
        "left": (x - distance, y),
    }[side]


def _preferred_middle_route(
    start: tuple[int, int],
    end: tuple[int, int],
    preference: PortPreference,
    lane_offset: int,
) -> list[tuple[int, int]]:
    if start[0] == end[0] or start[1] == end[1]:
        return [start, end]
    vertical = {preference.source, preference.target} <= {"top", "bottom"}
    horizontal = {preference.source, preference.target} <= {"left", "right"}
    if vertical:
        middle = _grid((start[1] + end[1]) / 2 + lane_offset)
        middle = _hold_off_faces(start[1], end[1], middle)
        return [start, (start[0], middle), (end[0], middle), end]
    if horizontal:
        middle = _hold_off_faces(start[0], end[0], _grid((start[0] + end[0]) / 2))
        return [start, (middle, start[1]), (middle, end[1]), end]
    return [start, (end[0], start[1]), end]


def _hold_off_faces(start: int, end: int, lane: int) -> int:
    """Keep a lane an arrowhead clear of both faces it runs between.

    A fan offset can push the lane up against a face, and the tip then lands on
    the corner it turned at (DG137). The authored stage's gaps are measured for
    its own arrows and its scenery is published, so the rule applies where the
    frame and the gaps are computed: a composed stage. When the faces are
    closer than two arrowheads there is no lane to hold, and the midpoint is
    the best the geometry allows.
    """
    if current_stage().is_default:
        return lane
    low, high = sorted((start, end))
    if high - low < 2 * ARROW_APPROACH:
        return lane
    # The bound is built from a face, which need not sit on the grid; the lane
    # must, because the label box is placed off it (DG121).
    return _grid(min(max(lane, low + ARROW_APPROACH), high - ARROW_APPROACH))


def _route_crosses_nodes(
    points: list[tuple[int, int]],
    boxes: dict[str, LayoutBox],
    allowed: set[str],
) -> bool:
    return any(
        node_id not in allowed
        and any(_segment_crosses_box(start, end, box) for start, end in zip(points, points[1:]))
        for node_id, box in boxes.items()
    )


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: LayoutBox) -> bool:
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return box.x < start[0] < box.x + box.w and low < box.y + box.h and high > box.y
    if start[1] == end[1]:
        low, high = sorted((start[0], end[0]))
        return box.y < start[1] < box.y + box.h and low < box.x + box.w and high > box.x
    return False


def _simplify_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for point in points:
        if result and point == result[-1]:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if a[0] == b[0] == c[0] or a[1] == b[1] == c[1]:
                result.pop(-2)
            else:
                break
    return result


def _spatial_preference(
    edge: VisualEdgePlan,
    default: PortPreference,
    boxes: dict[str, LayoutBox],
    preserve_layers: bool,
) -> PortPreference:
    source = boxes[edge.source]
    target = boxes[edge.target]
    dx = (target.x + target.w / 2) - (source.x + source.w / 2)
    dy = (target.y + target.h / 2) - (source.y + source.h / 2)
    if source.y + source.h <= target.y or target.y + target.h <= source.y:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    if preserve_layers and default.source in {"top", "bottom"} and default.target in {"top", "bottom"}:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    if abs(dx) > abs(dy) * 1.2:
        return PortPreference("right", "left") if dx >= 0 else PortPreference("left", "right")
    if abs(dy) > abs(dx) * 1.2:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    return default


def _fan_anchor(box: LayoutBox, side: str, index: int, count: int) -> tuple[int, int]:
    horizontal = side in {"top", "bottom"}
    length = box.w if horizontal else box.h
    if count == 1:
        offset = length / 2
    else:
        span = min(length - 24, max(FAN_GAP * (count - 1), length * 0.6))
        offset = (length - span) / 2 + index * span / (count - 1)
    offset = _grid(offset)
    if side == "top":
        return (_grid(box.x + offset), box.y)
    if side == "right":
        return (box.x + box.w, _grid(box.y + offset))
    if side == "bottom":
        return (_grid(box.x + offset), box.y + box.h)
    return (box.x, _grid(box.y + offset))


def _bounds_for(boxes: dict[str, LayoutBox], edges: list[LayoutEdge]) -> LayoutBox:
    xs: list[int] = []
    ys: list[int] = []
    for box in boxes.values():
        xs.extend((box.x, box.x + box.w))
        ys.extend((box.y, box.y + box.h))
    for edge in edges:
        for x, y in edge.points:
            xs.append(x)
            ys.append(y)
        if edge.label_box:
            xs.extend((edge.label_box.x, edge.label_box.x + edge.label_box.w))
            ys.extend((edge.label_box.y, edge.label_box.y + edge.label_box.h))
    if not xs:
        return LayoutBox(0, 0, 0, 0)
    return LayoutBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _grid(value: float | int) -> int:
    return int(round(float(value) / GRID) * GRID)
