from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union


ARCHITECTURE_LAYOUTS = {"horizontal-layers", "vertical-stack", "hub-and-spoke"}
ARCHITECTURE_NODE_KINDS = {"external", "service", "store", "cloud"}
ARCHITECTURE_EDGE_KINDS = {"primary", "secondary", "async"}
ARCHITECTURE_IMPORTANCE = {"primary", "secondary", "background"}
ARCHITECTURE_LIFECYCLE_PHASES = {"bootstrap", "runtime", "background", "shutdown"}
ARCHITECTURE_ROW_POLICIES = {"centered", "pipeline", "attachments-right"}
ARCHITECTURE_GROUP_LAYOUT_POLICIES = {"center-band", "pipeline", "sidecar", "stack"}
UML_TYPE_KINDS = {"class", "interface", "enum"}
UML_RELATIONSHIP_KINDS = {"inheritance", "association", "aggregation", "composition"}


@dataclass(frozen=True)
class LayerSpec:
    id: str
    label: str
    purpose: str | None = None
    order: int | None = None
    row_policy: str | None = None


@dataclass(frozen=True)
class GroupSpec:
    id: str
    label: str
    kind: str
    layer: str | None = None
    members: list[str] = field(default_factory=list)
    layout_policy: str | None = None
    side_label: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class LegendItemSpec:
    flow: str
    label: str
    reason: str | None = None


@dataclass(frozen=True)
class ArchitectureNodeSpec:
    id: str
    kind: str
    label: str
    layer: str | None = None
    sublabel: str | None = None
    role: str | None = None
    group: str | None = None
    description: str | None = None
    importance: str | None = None
    state_owner: bool | None = None
    lifecycle_phase: str | None = None


@dataclass(frozen=True)
class ArchitectureEdgeSpec:
    source: str
    target: str
    kind: str
    label: str | None = None
    flow: str | None = None
    interaction: str | None = None
    priority: str | None = None
    dashed: bool = False
    source_port: str | None = None
    target_port: str | None = None
    route_hint: str | None = None
    phase: str | None = None


@dataclass(frozen=True)
class ArchitectureDiagramSpec:
    kind: str
    title: str
    layout: str
    width: int = 960
    height: int = 540
    subtitle: str | None = None
    caption: str | None = None
    focus: str | None = None
    focus_path: list[str] = field(default_factory=list)
    focus_reason: str | None = None
    layers: list[LayerSpec] = field(default_factory=list)
    groups: list[GroupSpec] = field(default_factory=list)
    nodes: list[ArchitectureNodeSpec] = field(default_factory=list)
    edges: list[ArchitectureEdgeSpec] = field(default_factory=list)
    legend: list[LegendItemSpec] = field(default_factory=list)


@dataclass(frozen=True)
class UmlTypeSpec:
    id: str
    kind: str
    name: str
    attributes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    x: int | None = None
    y: int | None = None


@dataclass(frozen=True)
class UmlRelationshipSpec:
    source: str
    target: str
    kind: str
    label: str | None = None
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None
    route_policy: str | None = None
    label_lane: str | None = None
    label_offset: int | None = None


@dataclass(frozen=True)
class UmlClassDiagramSpec:
    kind: str
    title: str
    layout: str
    width: int = 960
    height: int = 640
    subtitle: str | None = None
    caption: str | None = None
    focus: str | None = None
    types: list[UmlTypeSpec] = field(default_factory=list)
    relationships: list[UmlRelationshipSpec] = field(default_factory=list)


DiagramSpec = Union[ArchitectureDiagramSpec, UmlClassDiagramSpec]


def _require(value: Any, message: str) -> Any:
    if value in (None, "", []):
        raise ValueError(message)
    return value


def _load_architecture(payload: dict[str, Any]) -> ArchitectureDiagramSpec:
    layout = _require(payload.get("layout"), "architecture layout is required")
    if layout not in ARCHITECTURE_LAYOUTS:
        raise ValueError(f"unsupported architecture layout: {layout}")

    layers = [
        LayerSpec(
            id=item["id"],
            label=item["label"],
            purpose=item.get("purpose"),
            order=item.get("order"),
            row_policy=item.get("row_policy"),
        )
        for item in payload.get("layers", [])
    ]
    for layer in layers:
        if layer.row_policy is not None and layer.row_policy not in ARCHITECTURE_ROW_POLICIES:
            raise ValueError(f"unsupported architecture row_policy: {layer.row_policy}")
    groups = [
        GroupSpec(
            id=item["id"],
            label=item["label"],
            kind=item["kind"],
            layer=item.get("layer"),
            members=list(item.get("members", [])),
            layout_policy=item.get("layout_policy"),
            side_label=item.get("side_label"),
            summary=item.get("summary"),
        )
        for item in payload.get("groups", [])
    ]
    for group in groups:
        if group.layout_policy is not None and group.layout_policy not in ARCHITECTURE_GROUP_LAYOUT_POLICIES:
            raise ValueError(f"unsupported architecture layout_policy: {group.layout_policy}")
    nodes = []
    for item in payload.get("nodes", []):
        kind = item["kind"]
        if kind not in ARCHITECTURE_NODE_KINDS:
            raise ValueError(f"unsupported architecture node kind: {kind}")
        importance = item.get("importance")
        if importance is not None and importance not in ARCHITECTURE_IMPORTANCE:
            raise ValueError(f"unsupported architecture importance: {importance}")
        lifecycle_phase = item.get("lifecycle_phase")
        if lifecycle_phase is not None and lifecycle_phase not in ARCHITECTURE_LIFECYCLE_PHASES:
            raise ValueError(f"unsupported architecture lifecycle_phase: {lifecycle_phase}")
        nodes.append(
            ArchitectureNodeSpec(
                id=item["id"],
                kind=kind,
                label=item["label"],
                layer=item.get("layer"),
                sublabel=item.get("sublabel"),
                role=item.get("role"),
                group=item.get("group"),
                description=item.get("description"),
                importance=importance,
                state_owner=item.get("state_owner"),
                lifecycle_phase=lifecycle_phase,
            )
        )

    edges = []
    for item in payload.get("edges", []):
        kind = item["kind"]
        if kind not in ARCHITECTURE_EDGE_KINDS:
            raise ValueError(f"unsupported architecture edge kind: {kind}")
        edges.append(
            ArchitectureEdgeSpec(
                source=item["source"],
                target=item["target"],
                kind=kind,
                label=item.get("label"),
                flow=item.get("flow"),
                interaction=item.get("interaction"),
                priority=item.get("priority"),
                dashed=bool(item.get("dashed", False)),
                source_port=item.get("source_port"),
                target_port=item.get("target_port"),
                route_hint=item.get("route_hint"),
                phase=item.get("phase"),
            )
        )

    legend = []
    for item in payload.get("legend", []):
        if isinstance(item, str):
            legend.append(LegendItemSpec(flow="unspecified", label=item))
        else:
            legend.append(
                LegendItemSpec(
                    flow=item["flow"],
                    label=item["label"],
                    reason=item.get("reason"),
                )
            )

    return ArchitectureDiagramSpec(
        kind="architecture",
        title=_require(payload.get("title"), "diagram title is required"),
        layout=layout,
        width=int(payload.get("width", 960)),
        height=int(payload.get("height", 540)),
        subtitle=payload.get("subtitle"),
        caption=payload.get("caption"),
        focus=payload.get("focus"),
        focus_path=list(payload.get("focus_path", [])),
        focus_reason=payload.get("focus_reason"),
        layers=layers,
        groups=groups,
        nodes=nodes,
        edges=edges,
        legend=legend,
    )


def _load_uml_class(payload: dict[str, Any]) -> UmlClassDiagramSpec:
    layout = _require(payload.get("layout"), "uml-class layout is required")
    if layout != "class-grid":
        raise ValueError(f"unsupported UML class layout: {layout}")

    types = []
    for item in payload.get("types", []):
        kind = item["kind"]
        if kind not in UML_TYPE_KINDS:
            raise ValueError(f"unsupported UML type kind: {kind}")
        types.append(
            UmlTypeSpec(
                id=item["id"],
                kind=kind,
                name=item["name"],
                attributes=list(item.get("attributes", [])),
                methods=list(item.get("methods", [])),
                x=item.get("x"),
                y=item.get("y"),
            )
        )

    relationships = []
    for item in payload.get("relationships", []):
        kind = item["kind"]
        if kind not in UML_RELATIONSHIP_KINDS:
            raise ValueError(f"unsupported UML relationship kind: {kind}")
        relationships.append(
            UmlRelationshipSpec(
                source=item["source"],
                target=item["target"],
                kind=kind,
                label=item.get("label"),
                source_multiplicity=item.get("source_multiplicity"),
                target_multiplicity=item.get("target_multiplicity"),
                route_policy=item.get("route_policy"),
                label_lane=item.get("label_lane"),
                label_offset=item.get("label_offset"),
            )
        )

    return UmlClassDiagramSpec(
        kind="uml-class",
        title=_require(payload.get("title"), "diagram title is required"),
        layout=layout,
        width=int(payload.get("width", 960)),
        height=int(payload.get("height", 640)),
        subtitle=payload.get("subtitle"),
        caption=payload.get("caption"),
        focus=payload.get("focus"),
        types=types,
        relationships=relationships,
    )


def load_diagram_spec(payload: dict[str, Any]) -> DiagramSpec:
    kind = _require(payload.get("kind"), "diagram kind is required")
    if kind == "architecture":
        return _load_architecture(payload)
    if kind == "uml-class":
        return _load_uml_class(payload)
    raise ValueError(f"unsupported diagram kind: {kind}")


def load_diagram_spec_file(path: str | Path) -> DiagramSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_diagram_spec(data)
