from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from .models import DrawingPlan


@dataclass(frozen=True)
class DrawingBundle:
    overview: DrawingPlan
    details: tuple[DrawingPlan, ...]
    navigation: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bundle_drawing(drawing: DrawingPlan, detail_limit: int = 9) -> DrawingBundle:
    """Create an explicit overview/detail bundle without silently dropping semantic nodes."""
    if drawing.kind != "architecture":
        raise ValueError("DrawingBundle currently supports architecture drawings only")
    if detail_limit < 2 or detail_limit > 9:
        raise ValueError("detail_limit must be between 2 and 9")
    groups: list[tuple[str, tuple[str, ...]]] = [
        (region.id, tuple(node_id for node_id in region.members if any(node.id == node_id for node in drawing.nodes)))
        for region in drawing.regions
        if region.members
    ]
    assigned = {node_id for _group, members in groups for node_id in members}
    ungrouped = tuple(node.id for node in drawing.nodes if node.id not in assigned)
    if ungrouped:
        groups.append(("ungrouped", ungrouped))
    if not groups:
        groups = [("drawing", tuple(node.id for node in drawing.nodes))]

    representative = {node_id: members[0] for _group, members in groups for node_id in members}
    overview_ids = tuple(dict.fromkeys(representative.values()))[:9]
    overview = _subset(drawing, overview_ids, f"{drawing.title} — Overview")
    mapped_edges = []
    seen_edges: set[tuple[str, str, str]] = set()
    node_by_id = {node.id: node for node in drawing.nodes}
    for edge in drawing.edges:
        source, target = representative.get(edge.source, edge.source), representative.get(edge.target, edge.target)
        key = (source, target, edge.channel)
        if source == target or source not in overview_ids or target not in overview_ids or key in seen_edges:
            continue
        seen_edges.add(key)
        mapped_edges.append(replace(edge, id=f"overview:{len(mapped_edges)}", source=source, target=target, label=None))
    overview = replace(overview, edges=tuple(mapped_edges))

    details = []
    navigation: dict[str, str] = {}
    for group_id, members in groups:
        for index in range(0, len(members), detail_limit):
            chunk = members[index:index + detail_limit]
            detail_id = f"{group_id}-{index // detail_limit + 1}"
            details.append(_subset(drawing, chunk, f"{drawing.title} — {detail_id}"))
            navigation.update({node_id: detail_id for node_id in chunk})
    if set(navigation) != set(node_by_id):
        raise ValueError("bundle navigation did not preserve every node")
    return DrawingBundle(overview, tuple(details), navigation)


def _subset(drawing: DrawingPlan, node_ids: tuple[str, ...], title: str) -> DrawingPlan:
    kept = set(node_ids)
    nodes = tuple(node for node in drawing.nodes if node.id in kept)
    edges = tuple(edge for edge in drawing.edges if edge.source in kept and edge.target in kept)
    regions = tuple(
        replace(region, members=tuple(node_id for node_id in region.members if node_id in kept))
        for region in drawing.regions
        if any(node_id in kept for node_id in region.members)
    )
    focus = drawing.hierarchy.focus_node if drawing.hierarchy.focus_node in kept else (node_ids[0] if node_ids else None)
    focus_path = tuple(node_id for node_id in drawing.hierarchy.focus_path if node_id in kept)
    return replace(
        drawing,
        title=title,
        nodes=nodes,
        edges=edges,
        regions=regions,
        annotations=tuple(annotation for annotation in drawing.annotations if annotation.target in kept or annotation.target == "diagram"),
        hierarchy=replace(drawing.hierarchy, focus_node=focus, focus_path=focus_path),
        composition=replace(
            drawing.composition,
            spine=tuple(node_id for node_id in drawing.composition.spine if node_id in kept),
            sidecars={key: tuple(item for item in value if item in kept) for key, value in drawing.composition.sidecars.items() if key in kept},
        ),
    )
