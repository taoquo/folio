from __future__ import annotations

from ..grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from ..models import DrawingPlan
from .models import DrawingDiagnostic


def validate_drawing_grammar(
    drawing: DrawingPlan,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    if drawing.composition.pattern not in grammar.composition_patterns:
        diagnostics.append(DrawingDiagnostic("ERROR", "DG020", "unknown composition pattern", drawing.composition.pattern))
    if drawing.composition.axis not in grammar.axes:
        diagnostics.append(DrawingDiagnostic("ERROR", "DG021", "unknown composition axis", drawing.composition.axis))
    for node in drawing.nodes:
        if node.archetype not in grammar.node_archetypes:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG022", "unknown node archetype", node.id))
        if node.emphasis not in grammar.emphasis_levels:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG023", "unknown node emphasis", node.id))
        if node.size_tier not in {item[0] for item in grammar.geometry.size_tiers}:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG027", "unknown node size tier", node.id))
        if node.pictogram and node.pictogram not in grammar.pictograms:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG028", "unknown pictogram", node.id))
    for edge in drawing.edges:
        if edge.channel not in grammar.edge_channels:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG024", "unknown edge channel", edge.id))
        if edge.emphasis not in grammar.emphasis_levels:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG025", "unknown edge emphasis", edge.id))
        if edge.direction != "forward":
            diagnostics.append(DrawingDiagnostic("ERROR", "DG037", "unsupported edge direction", edge.id))
        if edge.route_policy != "auto":
            diagnostics.append(DrawingDiagnostic("ERROR", "DG038", "unsupported route policy", edge.id))
    for region in drawing.regions:
        if region.treatment not in grammar.region_treatments:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG026", "unknown region treatment", region.id))
    for item in drawing.annotations:
        if item.target_kind not in {"node", "edge", "region", "diagram"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG029", "unknown annotation target kind", item.id))
        if item.kind not in {"note", "constraint", "risk", "navigation"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG030", "unknown annotation kind", item.id))
    if drawing.legend:
        for item in drawing.legend.items:
            if item.channel not in grammar.edge_channels:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG039", "unknown legend channel", item.channel))
    return diagnostics
