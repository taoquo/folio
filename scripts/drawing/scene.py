from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Union


@dataclass(frozen=True)
class SceneBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class SceneStyle:
    fill: str = "none"
    stroke: str = "none"
    stroke_width: float = 0
    dash: tuple[float, ...] = ()
    radius: int = 0
    fill_opacity: float | None = None


@dataclass(frozen=True)
class SceneText:
    text: str
    x: int
    y: int
    fill: str
    size: float
    family: str
    anchor: str = "start"
    tracking: float = 0
    weight: str | None = None
    klass: str | None = None


@dataclass(frozen=True)
class ArrowGeometry:
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ScenePictogram:
    id: str
    paths: tuple[str, ...]
    stroke: str


@dataclass(frozen=True)
class SceneNode:
    id: str
    box: SceneBox
    style: SceneStyle
    text_runs: tuple[SceneText, ...]
    pictogram: ScenePictogram | None = None
    shape: str = "rect"


@dataclass(frozen=True)
class SceneEdge:
    id: str
    source: str
    target: str
    points: tuple[tuple[int, int], ...]
    style: SceneStyle
    arrow: ArrowGeometry
    klass: str
    label: SceneText | None = None
    label_box: SceneBox | None = None
    corner_radius: int = 8
    bridges: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SceneRegion:
    id: str
    treatment: str
    label: SceneText
    box: SceneBox | None = None
    style: SceneStyle | None = None
    separator: tuple[tuple[int, int], tuple[int, int]] | None = None


@dataclass(frozen=True)
class SceneLegendItem:
    label: SceneText
    line: tuple[tuple[int, int], tuple[int, int]]
    arrow: ArrowGeometry
    stroke: str


@dataclass(frozen=True)
class SceneLegend:
    box: SceneBox
    style: SceneStyle
    title: SceneText
    items: tuple[SceneLegendItem, ...]


@dataclass(frozen=True)
class SceneAnnotation:
    id: str
    box: SceneBox
    style: SceneStyle
    text: SceneText
    leader: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SceneRect:
    id: str
    box: SceneBox
    style: SceneStyle
    klass: str | None = None


@dataclass(frozen=True)
class SceneLine:
    id: str
    start: tuple[int, int]
    end: tuple[int, int]
    style: SceneStyle
    klass: str | None = None


@dataclass(frozen=True)
class ScenePolyline:
    id: str
    points: tuple[tuple[int, int], ...]
    style: SceneStyle
    klass: str | None = None


@dataclass(frozen=True)
class ScenePath:
    id: str
    d: str
    style: SceneStyle
    klass: str | None = None


@dataclass(frozen=True)
class SceneCircle:
    id: str
    cx: int
    cy: int
    r: int
    style: SceneStyle
    klass: str | None = None


@dataclass(frozen=True)
class SceneClip:
    id: str
    box: SceneBox


@dataclass(frozen=True)
class SceneGroup:
    id: str
    children: tuple["ScenePrimitive", ...]
    clip_id: str | None = None
    klass: str | None = None


ScenePrimitive = Union[SceneRect, SceneLine, ScenePolyline, ScenePath, SceneCircle, SceneText, SceneClip, SceneGroup]


@dataclass(frozen=True)
class ResolvedScene:
    width: int
    height: int
    background: str
    title: SceneText
    regions: tuple[SceneRegion, ...]
    edges: tuple[SceneEdge, ...]
    nodes: tuple[SceneNode, ...]
    annotations: tuple[SceneAnnotation, ...] = ()
    legend: SceneLegend | None = None
    warnings: tuple[str, ...] = ()
    description: str | None = None
    language: str = "en"
    reading_order: tuple[str, ...] = ()
    primitives: tuple[ScenePrimitive, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
