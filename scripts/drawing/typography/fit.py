from __future__ import annotations

from dataclasses import dataclass

from ..models import NodeContentPlan
from .measure import measure_text


@dataclass(frozen=True)
class NodeContentLayout:
    eyebrow: str | None
    title: tuple[str, ...]
    metadata: str | None
    warnings: tuple[str, ...] = ()


def _wrap(text: str, max_width: float, font_size: float) -> tuple[str, ...]:
    if measure_text(text, font_size) <= max_width:
        return (text,)
    words = text.split()
    if len(words) == 1:
        split = max(1, len(text) // 2)
        return (text[:split], text[split:])
    lines = [""]
    for word in words:
        candidate = f"{lines[-1]} {word}".strip()
        if lines[-1] and measure_text(candidate, font_size) > max_width:
            lines.append(word)
        else:
            lines[-1] = candidate
    return tuple(lines[:2])


def fit_node_content(content: NodeContentPlan, width: int, height: int, reserve_right: int = 0) -> NodeContentLayout:
    max_width = width - 28 - reserve_right
    title = _wrap(content.title, max_width, 12)
    warnings = []
    if len(title) > 2 or any(measure_text(line, 12) > max_width for line in title):
        title = title[:2]
        warnings.append("node title exceeds two-line fit policy")
    metadata = content.metadata
    if metadata and measure_text(metadata, 9, "mono") > max_width and not content.metadata_required:
        metadata = None
        warnings.append("node metadata dropped to preserve minimum text size")
    if metadata and height < 54 and not content.metadata_required:
        metadata = None
        warnings.append("node metadata dropped after layout scaling")
    if len(title) == 2 and metadata and height <= 72 and not content.metadata_required:
        metadata = None
        warnings.append("node metadata dropped after title wrap")
    if metadata and content.metadata_required and measure_text(metadata, 9, "mono") > max_width:
        warnings.append("required node metadata exceeds available width")
    return NodeContentLayout(content.eyebrow, title, metadata, tuple(warnings))
