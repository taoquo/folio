from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PortPreference:
    source: str
    target: str


@dataclass(frozen=True)
class LayoutBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class LayoutEdge:
    source: str
    target: str
    points: list[tuple[int, int]]
    label: str | None = None
    label_box: LayoutBox | None = None
    id: str | None = None


@dataclass(frozen=True)
class LayoutResult:
    boxes: dict[str, LayoutBox]
    edges: list[LayoutEdge]
    bounds: LayoutBox
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LayoutConstraintSet:
    axis: str
    node_sizes: dict[str, tuple[int, int]]
    layer_order: tuple[str, ...]
    node_order: dict[str, tuple[str, ...]]
    preferred_adjacency: tuple[tuple[str, str], ...]
    spine: tuple[str, ...]
    sidecars: dict[str, tuple[str, ...]]
    port_preferences: dict[str, PortPreference]
    node_gap: int
    layer_gap: int
    edge_node_gap: int
    edge_edge_gap: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
