from __future__ import annotations

from ..grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from ..models import DrawingPlan
from .models import LayoutConstraintSet, PortPreference


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
        node_sizes={node.id: sizes[node.size_tier] for node in drawing.nodes},
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
