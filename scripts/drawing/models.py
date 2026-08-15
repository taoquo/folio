from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InformationBudget:
    target_density: int = 4
    max_nodes: int = 9
    max_focal_objects: int = 2
    max_edge_labels: int = 6
    max_regions: int = 4
    max_edges: int = 12


@dataclass(frozen=True)
class DrawingOverrides:
    composition: str | None = None
    focus_node: str | None = None
    spine: tuple[str, ...] | None = None
    node_order: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ReductionDecision:
    action: str
    targets: tuple[str, ...]
    reason: str
    applied: bool


@dataclass(frozen=True)
class CompositionPlan:
    pattern: str
    axis: str
    density: str
    spine: tuple[str, ...] = ()
    sidecars: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class HierarchyPlan:
    focus_node: str | None
    focus_path: tuple[str, ...]
    background_nodes: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeContentPlan:
    eyebrow: str | None
    title: str
    metadata: str | None
    description: str | None = None
    metadata_required: bool = False


@dataclass(frozen=True)
class VisualNodePlan:
    id: str
    archetype: str
    emphasis: str
    region: str | None
    content: NodeContentPlan
    pictogram: str | None = None
    size_tier: str = "regular"


@dataclass(frozen=True)
class VisualEdgePlan:
    id: str
    source: str
    target: str
    channel: str
    emphasis: str
    label: str | None = None
    direction: str = "forward"
    route_policy: str = "auto"


@dataclass(frozen=True)
class VisualRegionPlan:
    id: str
    role: str
    label: str
    members: tuple[str, ...]
    treatment: str


@dataclass(frozen=True)
class AnnotationPlan:
    id: str
    target: str
    target_kind: str
    kind: str
    text: str
    emphasis: str = "normal"


@dataclass(frozen=True)
class LegendItemPlan:
    channel: str
    label: str


@dataclass(frozen=True)
class LegendPlan:
    title: str
    items: tuple[LegendItemPlan, ...]


@dataclass(frozen=True)
class DrawingPlan:
    kind: str
    title: str
    composition: CompositionPlan
    hierarchy: HierarchyPlan
    regions: tuple[VisualRegionPlan, ...]
    nodes: tuple[VisualNodePlan, ...]
    edges: tuple[VisualEdgePlan, ...]
    annotations: tuple[AnnotationPlan, ...] = ()
    legend: LegendPlan | None = None
    width: int = 960
    height: int = 540
    subtitle: str | None = None
    caption: str | None = None
    explanation: tuple[str, ...] = ()
    reductions: tuple[ReductionDecision, ...] = ()
    schema_version: str = "2.0"
    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DrawingPlan":
        from .schema import normalize_plan_payload

        payload = normalize_plan_payload(payload)
        if payload.get("kind") != "architecture":
            raise ValueError("DrawingPlan.from_dict accepts architecture plans; use the Flowchart compiler for flowchart payloads")
        composition = payload["composition"]
        hierarchy = payload["hierarchy"]
        return cls(
            kind=payload["kind"],
            title=payload["title"],
            composition=CompositionPlan(
                pattern=composition["pattern"],
                axis=composition["axis"],
                density=composition.get("density", "restrained"),
                spine=tuple(composition.get("spine", ())),
                sidecars={key: tuple(value) for key, value in composition.get("sidecars", {}).items()},
            ),
            hierarchy=HierarchyPlan(
                focus_node=hierarchy.get("focus_node"),
                focus_path=tuple(hierarchy.get("focus_path", ())),
                background_nodes=tuple(hierarchy.get("background_nodes", ())),
            ),
            regions=tuple(
                VisualRegionPlan(item["id"], item["role"], item["label"], tuple(item.get("members", ())), item["treatment"])
                for item in payload.get("regions", ())
            ),
            nodes=tuple(
                VisualNodePlan(
                    id=item["id"],
                    archetype=item["archetype"],
                    emphasis=item["emphasis"],
                    region=item.get("region"),
                    content=NodeContentPlan(**item["content"]),
                    pictogram=item.get("pictogram"),
                    size_tier=item.get("size_tier", "regular"),
                )
                for item in payload.get("nodes", ())
            ),
            edges=tuple(
                VisualEdgePlan(
                    id=item["id"],
                    source=item["source"],
                    target=item["target"],
                    channel=item["channel"],
                    emphasis=item["emphasis"],
                    label=item.get("label"),
                    direction=item.get("direction", "forward"),
                    route_policy=item.get("route_policy", "auto"),
                )
                for item in payload.get("edges", ())
            ),
            annotations=tuple(
                AnnotationPlan(
                    item.get("id", f"annotation:{index}") if isinstance(item, dict) else f"annotation:{index}",
                    item.get("target", "diagram") if isinstance(item, dict) else "diagram",
                    item.get("target_kind", "diagram") if isinstance(item, dict) else "diagram",
                    item.get("kind", "note") if isinstance(item, dict) else "note",
                    item["text"] if isinstance(item, dict) else str(item),
                    item.get("emphasis", "normal") if isinstance(item, dict) else "normal",
                )
                for index, item in enumerate(payload.get("annotations", ()))
            ),
            legend=_legend_from_payload(payload.get("legend")),
            width=int(payload.get("width", 960)),
            height=int(payload.get("height", 540)),
            subtitle=payload.get("subtitle"),
            caption=payload.get("caption"),
            explanation=tuple(payload.get("explanation", ())),
            reductions=tuple(
                ReductionDecision(
                    item["action"],
                    tuple(item.get("targets", ())),
                    item["reason"],
                    bool(item.get("applied", False)),
                )
                for item in payload.get("reductions", ())
            ),
            schema_version=str(payload.get("schema_version", "2.0")),
            language=str(payload.get("language", "en")),
        )


def _legend_from_payload(payload: Any) -> LegendPlan | None:
    if not payload:
        return None
    if isinstance(payload, list):
        return LegendPlan("LEGEND", tuple(LegendItemPlan(item["channel"], item["label"]) for item in payload))
    return LegendPlan(
        str(payload.get("title", "LEGEND")),
        tuple(LegendItemPlan(item["channel"], item["label"]) for item in payload.get("items", ())),
    )
