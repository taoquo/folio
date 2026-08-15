from __future__ import annotations

from ..models import DrawingPlan
from ..scene import ResolvedScene
from .metrics import crossing_count
from .models import DrawingDiagnostic


def _bends(points: tuple[tuple[int, int], ...]) -> int:
    return max(0, len(points) - 2)


def diagnose_taste(drawing: DrawingPlan, scene: ResolvedScene) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    total_bends = sum(_bends(edge.points) for edge in scene.edges)
    spine_pairs = set(zip(drawing.composition.spine, drawing.composition.spine[1:]))
    spine_bends = sum(_bends(edge.points) for edge in scene.edges if (edge.source, edge.target) in spine_pairs)
    if spine_bends > 3:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG201", f"primary spine contains {spine_bends} bends; preferred <= 3"))
    labelled = sum(1 for edge in scene.edges if edge.label)
    if drawing.edges and labelled / len(drawing.edges) > 0.75:
        diagnostics.append(DrawingDiagnostic("WARNING", "DG118", f"{labelled} of {len(drawing.edges)} edges have labels; diagram may be over-annotated"))
    if total_bends > max(6, len(scene.edges) * 2):
        diagnostics.append(DrawingDiagnostic("TASTE", "DG202", f"diagram contains {total_bends} connector bends"))
    crossings = crossing_count(scene)
    if crossings:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG204", f"diagram contains {crossings} connector crossings"))
    if len(drawing.nodes) >= 8:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG203", f"diagram density is high at {len(drawing.nodes)} nodes"))
    if len(drawing.edges) > 12:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG205", f"diagram contains {len(drawing.edges)} edges; preferred <= 12"))
    focal = sum(1 for node in drawing.nodes if node.emphasis == "focal")
    if focal == 0:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG206", "diagram has no focal object"))
    layer_centers = []
    for region in drawing.regions:
        if region.treatment != "layer-band":
            continue
        members = [node.box.y + node.box.h / 2 for node in scene.nodes if node.id in region.members]
        if members:
            layer_centers.append(sum(members) / len(members))
    gaps = [right - left for left, right in zip(layer_centers, layer_centers[1:])]
    if len(gaps) >= 2 and max(gaps) - min(gaps) > 32:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG207", "layer spacing varies by more than 32 units"))
    return diagnostics
