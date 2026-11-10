from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..connectors.labels import NODE_CLEARANCE, compact_edge_label, label_width
from ..grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR, ArchitectureGrammar
from ..models import DrawingPlan, VisualEdgePlan
from ..stage import current as current_stage
from ..typography.fit import METADATA_TWO_LINE_HEIGHT, fit_node_content, metadata_lines
from .models import LayoutConstraintSet, PortPreference


def _node_sizes(drawing: DrawingPlan, sizes: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """The tier boxes, made tall enough for a descriptor that wraps to two lines.

    A composed stage shrinks the box until it holds the title and no longer the
    line under it. Wrapping the descriptor costs twelve units of height and
    keeps the meaning, so the boxes that need them ask for them.

    The plate decides once, the same way the scene does: one node whose
    descriptor cannot be held at all means the plate shows titles only, and a
    box must not reserve height for a line the plate will not draw. That is why
    every fit is computed before any height is raised.
    """
    if current_stage().is_default:
        return {node.id: sizes[node.size_tier] for node in drawing.nodes}
    planned: dict[str, tuple[int, int, bool, bool]] = {}
    for node in drawing.nodes:
        width, height = sizes[node.size_tier]
        reserve = 24 if node.pictogram else 0
        wrapped = len(metadata_lines(node.content.metadata or "", width - 28 - reserve, wrap=True)) == 2
        # Ask the same question the scene will ask of the box this node would
        # get, so the plate's answer here and there cannot disagree.
        fitted = fit_node_content(
            node.content, width, max(height, METADATA_TWO_LINE_HEIGHT) if wrapped else height,
            reserve_right=reserve)
        planned[node.id] = (width, height, wrapped, bool(fitted.metadata))
    if any(node.content.metadata and not planned[node.id][3] for node in drawing.nodes):
        return {node_id: (width, height) for node_id, (width, height, _, _) in planned.items()}
    return {
        node_id: (width, max(height, METADATA_TWO_LINE_HEIGHT) if wrapped else height)
        for node_id, (width, height, wrapped, _) in planned.items()
    }


def row_gap_requirements(
    ordered: Sequence[str],
    edges: Iterable[VisualEdgePlan],
    constraints: LayoutConstraintSet,
    minimum_gap: int | None = None,
    *,
    reserve_labels: bool = True,
) -> list[int]:
    """The least gap each adjacent pair in a row needs to keep its label.

    A connector label is drawn *beside* its line, in the gap between two node
    boxes. The placer refuses a label that touches a box, so a 48-unit gap and
    a 48-unit label leave the word nowhere to go and the edge silently loses
    it: `dispatch` disappears from every plate of a drawing that names it.

    The layout therefore reserves the label's width before it places anything,
    using the same measurement and the same two-line cap the placer uses. The
    reservation is the box plus the clearance the placer keeps from each node,
    not the gap it keeps from the connector -- a wider reservation buys nothing
    and costs the plate type size, because the frame is the row's ink.

    ``reserve_labels=False`` answers a different question: would the reading
    group fit at its ordinary gap? A row is not split for a label, because
    splitting reshapes the plate; the label is served out of the room the row
    already has, and a row that has none keeps its shape and drops the word.
    """
    base = constraints.node_gap if minimum_gap is None else minimum_gap
    by_pair: dict[frozenset[str], int] = {}
    for edge in (edges if reserve_labels else ()):
        label = compact_edge_label(edge.label)
        if not label:
            continue
        pair = frozenset((edge.source, edge.target))
        by_pair[pair] = max(
            by_pair.get(pair, 0), label_width(label) + 2 * NODE_CLEARANCE)
    return [
        max(base, by_pair.get(frozenset((left, right)), 0))
        for left, right in zip(ordered, ordered[1:])
    ]


def compile_layout_constraints(
    drawing: DrawingPlan,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> LayoutConstraintSet:
    geometry = grammar.geometry
    sizes = {name: (width, height) for name, width, height in geometry.size_tiers}
    layer_order = tuple(region.id for region in drawing.regions if region.treatment == "layer-band")
    node_order: dict[str, tuple[str, ...]] = {}
    for region in drawing.regions:
        if region.treatment == "layer-band":
            node_order[region.id] = region.members
    ports: dict[str, PortPreference] = {}
    for edge in drawing.edges:
        if drawing.composition.axis == "left-right":
            preference = PortPreference("right", "left")
        else:
            source_region = next((node.region for node in drawing.nodes if node.id == edge.source), None)
            target_region = next((node.region for node in drawing.nodes if node.id == edge.target), None)
            preference = PortPreference("bottom", "top") if source_region != target_region else PortPreference("right", "left")
        ports[edge.id] = preference
    return LayoutConstraintSet(
        axis=drawing.composition.axis,
        node_sizes=_node_sizes(drawing, sizes),
        layer_order=layer_order,
        node_order=node_order,
        preferred_adjacency=tuple(zip(drawing.composition.spine, drawing.composition.spine[1:])),
        spine=drawing.composition.spine,
        sidecars=drawing.composition.sidecars,
        port_preferences=ports,
        node_gap=geometry.node_gap,
        layer_gap=geometry.layer_gap,
        edge_node_gap=geometry.edge_node_gap,
        edge_edge_gap=geometry.edge_edge_gap,
    )
