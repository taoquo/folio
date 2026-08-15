from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..theme.folio import FolioTheme


class TextRole(str, Enum):
    DIAGRAM_TITLE = "diagram-title"
    DIAGRAM_SUBTITLE = "diagram-subtitle"
    REGION_LABEL = "region-label"
    NODE_EYEBROW = "node-eyebrow"
    NODE_TITLE = "node-title"
    NODE_META = "node-meta"
    EDGE_LABEL = "edge-label"
    ANNOTATION = "annotation"
    LEGEND = "legend"


@dataclass(frozen=True)
class TextStyle:
    family: str
    size: float
    color: str
    anchor: str = "start"
    tracking: float = 0
    weight: str | None = None


def resolve_text_style(role: TextRole, theme: FolioTheme) -> TextStyle:
    styles = {
        TextRole.DIAGRAM_TITLE: TextStyle(theme.serif, 24, theme.near_black, "middle"),
        TextRole.DIAGRAM_SUBTITLE: TextStyle(theme.serif, 11, theme.olive, "middle"),
        TextRole.REGION_LABEL: TextStyle(theme.mono, 11, theme.stone, tracking=0.08),
        TextRole.NODE_EYEBROW: TextStyle(theme.mono, 7, theme.stone, tracking=0.15),
        TextRole.NODE_TITLE: TextStyle(theme.serif, 12, theme.near_black, "middle", weight="500"),
        TextRole.NODE_META: TextStyle(theme.mono, 9, theme.olive, "middle"),
        TextRole.EDGE_LABEL: TextStyle(theme.mono, 8, theme.stone, "middle"),
        TextRole.ANNOTATION: TextStyle(theme.serif, 10, theme.olive),
        TextRole.LEGEND: TextStyle(theme.mono, 9, theme.near_black),
    }
    return styles[role]
