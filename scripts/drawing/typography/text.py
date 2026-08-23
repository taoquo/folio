"""Language inference, wrapping, and canvas sizing shared by every family."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..canvas_contract import CANVAS_WIDTH, GRAPH_CANVAS, CanvasBand
from .measure import measure_text


def infer_language(title: str, labels: Iterable[str], explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    text = title + "".join(labels)
    return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"


def wrap_text(text: str, width: int, size: float, family: str, max_lines: int = 2) -> tuple[str, ...]:
    if measure_text(text, size, family) <= width:
        return (text,)
    words = text.split()
    if len(words) <= 1:
        limit = max(2, int(width / max(1, size)))
        return tuple(text[index:index + limit] for index in range(0, min(len(text), limit * max_lines), limit))
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and measure_text(candidate, size, family) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines[:max_lines])


def dimensions(
    payload: dict[str, Any],
    default_height: int | None = None,
    band: CanvasBand = GRAPH_CANVAS,
) -> tuple[int, int]:
    """Resolve the stage size, clamping an out-of-band height back to the family default.

    ``common_payload_diagnostics`` already reports the bad value, so this only keeps the
    layout math safe until the diagnostics are raised.
    """
    return CANVAS_WIDTH, band.resolve(payload, default_height)
