from __future__ import annotations

from dataclasses import asdict, dataclass

from ..models import DrawingPlan
from ..scene import ResolvedScene
from .geometry import validate_scene_geometry


@dataclass(frozen=True)
class DrawingMetrics:
    semantic_nodes: int
    visual_nodes: int
    edges: int
    edge_labels: int
    focus: int
    crossings: int
    bends: int
    spine_bends: int
    text_overflow: int
    layout_warnings: int
    taste_warnings: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _crosses(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int], d: tuple[int, int]) -> bool:
    if a[0] == b[0] and c[1] == d[1]:
        return min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1])
    if a[1] == b[1] and c[0] == d[0]:
        return min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1])
    return False


def crossing_count(scene: ResolvedScene) -> int:
    count = 0
    for index, left in enumerate(scene.edges):
        for right in scene.edges[index + 1:]:
            if {left.source, left.target} & {right.source, right.target}:
                continue
            if any(
                _crosses(a, b, c, d) or _crosses(c, d, a, b)
                for a, b in zip(left.points, left.points[1:])
                for c, d in zip(right.points, right.points[1:])
            ):
                count += 1
    return count


def collect_metrics(
    drawing: DrawingPlan,
    scene: ResolvedScene,
    semantic_node_count: int | None = None,
    taste_warning_count: int | None = None,
) -> DrawingMetrics:
    geometry = validate_scene_geometry(scene)
    spine_pairs = set(zip(drawing.composition.spine, drawing.composition.spine[1:]))
    bends = {edge.id: max(0, len(edge.points) - 2) for edge in scene.edges}
    spine_bends = sum(
        bends[edge.id]
        for edge in scene.edges
        if (edge.source, edge.target) in spine_pairs
    )
    if taste_warning_count is None:
        from .taste import diagnose_taste

        taste_warning_count = len(diagnose_taste(drawing, scene))
    return DrawingMetrics(
        semantic_nodes=semantic_node_count if semantic_node_count is not None else len(drawing.nodes),
        visual_nodes=len(scene.nodes),
        edges=len(scene.edges),
        edge_labels=sum(1 for edge in scene.edges if edge.label),
        focus=sum(1 for node in drawing.nodes if node.emphasis == "focal"),
        crossings=crossing_count(scene),
        bends=sum(bends.values()),
        spine_bends=spine_bends,
        text_overflow=sum(1 for item in geometry if item.code in {"DG108", "DG111"}),
        layout_warnings=len(scene.warnings),
        taste_warnings=taste_warning_count,
    )


def collect_scene_metrics(
    scene: ResolvedScene,
    *,
    semantic_count: int,
    visual_count: int | None = None,
    focus_count: int = 0,
    taste_warning_count: int = 0,
    edge_count: int | None = None,
    edge_label_count: int | None = None,
    bend_count: int | None = None,
) -> DrawingMetrics:
    geometry = validate_scene_geometry(scene)
    bends = [max(0, len(edge.points) - 2) for edge in scene.edges]
    return DrawingMetrics(
        semantic_nodes=semantic_count,
        visual_nodes=visual_count if visual_count is not None else len(scene.nodes),
        edges=edge_count if edge_count is not None else len(scene.edges),
        edge_labels=edge_label_count if edge_label_count is not None else sum(1 for edge in scene.edges if edge.label),
        focus=focus_count,
        crossings=crossing_count(scene),
        bends=bend_count if bend_count is not None else sum(bends),
        spine_bends=0,
        text_overflow=sum(1 for item in geometry if item.code in {"DG108", "DG111"}),
        layout_warnings=len(scene.warnings),
        taste_warnings=taste_warning_count,
    )
