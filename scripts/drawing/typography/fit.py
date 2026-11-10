from __future__ import annotations

from dataclasses import dataclass

from ..models import NodeContentPlan
from ..stage import current as current_stage
from .measure import measure_text


@dataclass(frozen=True)
class NodeContentLayout:
    eyebrow: str | None
    title: tuple[str, ...]
    # The descriptor is one line at the authored stage and may become two on a
    # composed one: a narrower box holds the same words only by wrapping them.
    metadata: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# The least box that holds an eyebrow, a one-line title and two descriptor
# lines: the eyebrow sits at +20, the title at +40 and the descriptor at +56,
# so a second descriptor line lands at +68 and needs eight units under it.
METADATA_TWO_LINE_HEIGHT = 76


def metadata_lines(text: str, max_width: float, *, wrap: bool = False) -> tuple[str, ...]:
    """The descriptor as one or two monospaced lines, or nothing if it cannot fit.

    A descriptor that fits is one line. One that does not is split at a word
    boundary, but only when the caller has room to grow the box for the second
    line (`wrap`): the authored stage publishes fixed 72-unit boxes, so there it
    keeps the single-line rule and drops the line instead. Past two lines the
    box would have to grow again for a line the reader can live without, so the
    descriptor is dropped and the caller is told, the same way a title that
    cannot fit is reported.
    """
    if not text:
        return ()
    if measure_text(text, 9, "mono") <= max_width:
        return (text,)
    if not wrap:
        return ()
    lines = [""]
    for word in text.split():
        candidate = f"{lines[-1]} {word}".strip()
        if lines[-1] and measure_text(candidate, 9, "mono") > max_width:
            lines.append(word)
        else:
            lines[-1] = candidate
    if len(lines) > 2 or any(measure_text(line, 9, "mono") > max_width for line in lines):
        return ()
    return tuple(lines)


def wrap_line_count(text: str, max_width: float, font_size: float) -> int:
    """How many lines this text needs, with no two-line cap.

    ``_wrap`` drops everything past the second line, which is right for a box
    that has already been sized and wrong while sizing it: a title that needs
    three lines would be measured as two and lose a word in the drawing.
    """
    if measure_text(text, font_size) <= max_width:
        return 1
    lines = [""]
    for word in text.split():
        candidate = f"{lines[-1]} {word}".strip()
        if lines[-1] and measure_text(candidate, font_size) > max_width:
            lines.append(word)
        else:
            lines[-1] = candidate
    return len(lines)


def fit_wrap_width(
    text: str,
    width: int,
    font_size: float,
    max_lines: int,
    inset: int,
    limit: int = 1024,
) -> int:
    """Widen a box on the 4-unit grid until ``text`` wraps within ``max_lines``.

    The alternative is a box that keeps its width and loses the tail of its
    label, which is how a state called "Share with board" becomes "Share with".
    """
    width = max(48, width)
    while width < limit and wrap_line_count(
            text, max(48, width - inset), font_size) > max_lines:
        width = (width // 4 + 1) * 4
    return width


def _wrap(text: str, max_width: float, font_size: float) -> tuple[str, ...]:
    if measure_text(text, font_size) <= max_width:
        return (text,)
    words = text.split()
    if len(words) == 1:
        if not current_stage().is_default:
            # On a composed-for-the-column stage a word that does not fit is a
            # composition failure, not a licence to cut it in half: `Posit` /
            # `ional` passes every geometry check and is unreadable. Return it
            # whole so DG111 reports it and the stage search picks a wider
            # stage or the fixture gets a shorter label.
            return (text,)
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
    metadata = metadata_lines(content.metadata or "", max_width, wrap=not current_stage().is_default)
    if content.metadata and not metadata and not content.metadata_required:
        warnings.append("node metadata dropped to preserve minimum text size")
    if metadata and not content.metadata_required:
        if height < 54:
            metadata = ()
            warnings.append("node metadata dropped after layout scaling")
        elif len(metadata) == 2 and height < METADATA_TWO_LINE_HEIGHT:
            # Two lines are only drawn where the box was made tall enough for
            # them; the planner asks for that height, and a box that did not
            # get it keeps the title instead of overflowing.
            metadata = ()
            warnings.append("node metadata dropped after layout scaling")
        elif len(title) == 2 and len(metadata) == 1 and height <= 72:
            metadata = ()
            warnings.append("node metadata dropped after title wrap")
    if content.metadata and content.metadata_required and not metadata:
        warnings.append("required node metadata exceeds available width")
    return NodeContentLayout(content.eyebrow, title, metadata, tuple(warnings))
