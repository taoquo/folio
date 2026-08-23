from __future__ import annotations

from ..models import DrawingPlan
from ..scene import ResolvedScene
from .metrics import crossing_count
from .models import DrawingDiagnostic


def _bends(points: tuple[tuple[int, int], ...]) -> int:
    return max(0, len(points) - 2)


def diagnose_connector_collisions(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    """Geometry-only connector faults, valid for any family that routes edges.

    Kept separate from :func:`diagnose_taste` because the rest of that function is calibrated
    against the architecture grammar: its spine-bend, density and focal-object thresholds all
    assume a layered component diagram. A flowchart with a decision needs bends by
    construction, carries its own budgets in FC001/FC002/FC201, and has no focal object at
    all, so importing those thresholds wholesale reports faults that are not faults. A
    connector crossing another connector is wrong everywhere.
    """
    crossings = crossing_count(scene)
    if not crossings:
        return []
    return [DrawingDiagnostic("TASTE", "DG204", f"diagram contains {crossings} connector crossings")]


def diagnose_taste(drawing: DrawingPlan, scene: ResolvedScene) -> list[DrawingDiagnostic]:
    """Aesthetic diagnostics shared by every graph family.

    ``drawing`` only has to expose ``composition.spine``, ``nodes`` and ``edges``. Region
    banding is read defensively so families without a region model -- flowcharts, for one --
    can still be gated on crossings, bends and focus.
    """
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
    for region in getattr(drawing, "regions", ()):
        if region.treatment != "layer-band":
            continue
        members = [node.box.y + node.box.h / 2 for node in scene.nodes if node.id in region.members]
        if members:
            layer_centers.append(sum(members) / len(members))
    gaps = [right - left for left, right in zip(layer_centers, layer_centers[1:])]
    if len(gaps) >= 2 and max(gaps) - min(gaps) > 32:
        diagnostics.append(DrawingDiagnostic("TASTE", "DG207", "layer spacing varies by more than 32 units"))
    return diagnostics
