from __future__ import annotations

from collections import Counter

from ..models import DrawingPlan, InformationBudget
from .models import DrawingDiagnostic


def validate_drawing_semantics(drawing: DrawingPlan, budget: InformationBudget = InformationBudget()) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    node_ids = [node.id for node in drawing.nodes]
    duplicates = [node_id for node_id, count in Counter(node_ids).items() if count > 1]
    diagnostics.extend(DrawingDiagnostic("ERROR", "DG001", "duplicate node id", item) for item in duplicates)
    known = set(node_ids)
    edge_ids = [edge.id for edge in drawing.edges]
    region_ids = [region.id for region in drawing.regions]
    annotation_ids = [item.id for item in drawing.annotations]
    diagnostics.extend(DrawingDiagnostic("ERROR", "DG018", "duplicate edge id", item) for item, count in Counter(edge_ids).items() if count > 1)
    diagnostics.extend(DrawingDiagnostic("ERROR", "DG019", "duplicate region id", item) for item, count in Counter(region_ids).items() if count > 1)
    diagnostics.extend(DrawingDiagnostic("ERROR", "DG031", "duplicate annotation id", item) for item, count in Counter(annotation_ids).items() if count > 1)
    if len(node_ids) > budget.max_nodes:
        diagnostics.append(DrawingDiagnostic("ERROR", "DG002", f"{len(node_ids)} nodes exceed budget {budget.max_nodes}; split the diagram"))
    if len(drawing.edges) > budget.max_edges:
        diagnostics.append(DrawingDiagnostic("WARNING", "DG014", f"{len(drawing.edges)} edges exceed preferred budget {budget.max_edges}; reduce or split the diagram"))
    focal = [node.id for node in drawing.nodes if node.emphasis == "focal"]
    if len(focal) > budget.max_focal_objects:
        diagnostics.append(DrawingDiagnostic("ERROR", "DG003", f"{len(focal)} focal objects exceed budget {budget.max_focal_objects}"))
    for edge in drawing.edges:
        if edge.source not in known or edge.target not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG004", "edge references an unknown node", edge.id))
        if edge.source == edge.target:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG043", "edge cannot start and end on the same node", edge.id))
    drawn_edges: dict[tuple[str, str, str], set[str]] = {}
    for edge in drawing.edges:
        signature = (edge.label or "").strip()
        bucket = drawn_edges.setdefault((edge.source, edge.target, edge.channel), set())
        if signature in bucket:
            diagnostics.append(DrawingDiagnostic(
                "ERROR", "DG042",
                "parallel edges between the same pair need a distinct label or channel", edge.id,
            ))
        bucket.add(signature)
    edge_labels = sum(1 for edge in drawing.edges if edge.label)
    if edge_labels > budget.max_edge_labels:
        diagnostics.append(DrawingDiagnostic("WARNING", "DG008", f"{edge_labels} edge labels exceed preferred budget {budget.max_edge_labels}"))
    if len(drawing.regions) > budget.max_regions:
        diagnostics.append(DrawingDiagnostic("WARNING", "DG009", f"{len(drawing.regions)} regions exceed preferred budget {budget.max_regions}"))
    for region in drawing.regions:
        if not region.members:
            diagnostics.append(DrawingDiagnostic("WARNING", "DG005", "region has no members", region.id))
        for member in region.members:
            if member not in known:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG006", "region references an unknown node", member))
    known_regions = set(region_ids)
    for node in drawing.nodes:
        if node.region is not None and node.region not in known_regions:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG032", "node references an unknown region", node.id))
    for item in drawing.composition.spine:
        if item not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG007", "spine references an unknown node", item))
    known_edges = {(edge.source, edge.target) for edge in drawing.edges}
    for source, target in zip(drawing.composition.spine, drawing.composition.spine[1:]):
        if (source, target) not in known_edges:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG010", "spine step has no matching edge", f"{source}->{target}"))
    for owner, sidecars in drawing.composition.sidecars.items():
        if owner not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG011", "sidecar owner is unknown", owner))
        for sidecar in sidecars:
            if sidecar not in known:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG012", "sidecar node is unknown", sidecar))
    if drawing.hierarchy.focus_node and drawing.hierarchy.focus_node not in known:
        diagnostics.append(DrawingDiagnostic("ERROR", "DG013", "focus node is unknown", drawing.hierarchy.focus_node))
    for node_id in drawing.hierarchy.focus_path:
        if node_id not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG033", "focus path references an unknown node", node_id))
    for source, target in zip(drawing.hierarchy.focus_path, drawing.hierarchy.focus_path[1:]):
        if (source, target) not in known_edges:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG034", "focus path step has no matching edge", f"{source}->{target}"))
    for node_id in drawing.hierarchy.background_nodes:
        if node_id not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG035", "background node is unknown", node_id))
        elif next(node for node in drawing.nodes if node.id == node_id).emphasis != "background":
            diagnostics.append(DrawingDiagnostic("ERROR", "DG040", "background node must use background emphasis", node_id))
    if drawing.hierarchy.focus_node and drawing.hierarchy.focus_node in known:
        focus_node = next(node for node in drawing.nodes if node.id == drawing.hierarchy.focus_node)
        if focus_node.emphasis != "focal":
            diagnostics.append(DrawingDiagnostic("ERROR", "DG041", "focus node must use focal emphasis", focus_node.id))
    known_reduction_targets = known | {edge.id for edge in drawing.edges}
    for decision in drawing.reductions:
        if decision.action not in {"merge", "drop", "background", "split"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG015", "unknown information reduction action", decision.action))
        for target in decision.targets:
            if target not in known_reduction_targets:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG016", "reduction references an unknown target", target))
    known_annotation_targets = known | {edge.id for edge in drawing.edges} | {region.id for region in drawing.regions} | {"diagram"}
    for item in drawing.annotations:
        if item.target not in known_annotation_targets:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG017", "annotation references an unknown target", item.id))
        expected_targets = {
            "node": known,
            "edge": set(edge_ids),
            "region": known_regions,
            "diagram": {"diagram"},
        }
        if item.target_kind in expected_targets and item.target not in expected_targets[item.target_kind]:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG036", "annotation target does not match target_kind", item.id))
    return diagnostics
