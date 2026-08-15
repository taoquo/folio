from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SemanticNode:
    id: str
    label: str
    role: str
    description: str | None = None
    importance: str = "normal"
    state_owner: bool = False
    lifecycle_phase: str | None = None
    domain: str | None = None
    metadata: str | None = None


@dataclass(frozen=True)
class SemanticEdge:
    id: str
    source: str
    target: str
    relation: str
    interaction: str | None = None
    importance: str = "normal"
    phase: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class SemanticGroup:
    id: str
    label: str
    members: tuple[str, ...]
    role: str | None = None
    domain: str | None = None


@dataclass(frozen=True)
class SemanticDiagram:
    title: str
    nodes: tuple[SemanticNode, ...]
    edges: tuple[SemanticEdge, ...]
    groups: tuple[SemanticGroup, ...]
    focus_candidates: tuple[str, ...] = ()
    focus_path: tuple[str, ...] = ()
    narrative: str | None = None
    width: int = 960
    height: int = 540
    subtitle: str | None = None
    caption: str | None = None
    layer_order: tuple[str, ...] = ()
    layer_labels: dict[str, str] = field(default_factory=dict)
    composition_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
