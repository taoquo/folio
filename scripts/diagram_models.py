from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union


ARCHITECTURE_LAYOUTS = {"horizontal-layers", "vertical-stack", "hub-and-spoke"}
ARCHITECTURE_NODE_KINDS = {"external", "service", "store", "cloud"}
ARCHITECTURE_EDGE_KINDS = {"primary", "secondary", "async"}
UML_TYPE_KINDS = {"class", "interface", "enum"}
UML_RELATIONSHIP_KINDS = {"inheritance", "association", "aggregation", "composition"}


@dataclass(frozen=True)
class LayerSpec:
    id: str
    label: str


@dataclass(frozen=True)
class ArchitectureNodeSpec:
    id: str
    kind: str
    label: str
    layer: str | None = None
    sublabel: str | None = None


@dataclass(frozen=True)
class ArchitectureEdgeSpec:
    source: str
    target: str
    kind: str
    label: str | None = None


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
    layers: list[LayerSpec] = field(default_factory=list)
    nodes: list[ArchitectureNodeSpec] = field(default_factory=list)
    edges: list[ArchitectureEdgeSpec] = field(default_factory=list)
    legend: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UmlTypeSpec:
    id: str
    kind: str
    name: str
    attributes: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UmlRelationshipSpec:
    source: str
    target: str
    kind: str
    label: str | None = None
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None


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

    layers = [LayerSpec(id=item["id"], label=item["label"]) for item in payload.get("layers", [])]
    nodes = []
    for item in payload.get("nodes", []):
        kind = item["kind"]
        if kind not in ARCHITECTURE_NODE_KINDS:
            raise ValueError(f"unsupported architecture node kind: {kind}")
        nodes.append(
            ArchitectureNodeSpec(
                id=item["id"],
                kind=kind,
                label=item["label"],
                layer=item.get("layer"),
                sublabel=item.get("sublabel"),
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
        layers=layers,
        nodes=nodes,
        edges=edges,
        legend=list(payload.get("legend", [])),
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
