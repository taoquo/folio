"""Text roles: the single place a diagram decides how words look.

Every ``SceneText`` colour and size resolves through :func:`resolve_text_style`. That matters
because the alternative was tried: with the roles defined here but only a tenth of call sites
using them, the table described an intent that the output did not follow, and the same
question -- how dark should a 7pt label be -- got answered independently in eighty places.

Two axes carry hierarchy, and they pull in opposite directions on purpose:

* **Size and tracking** carry rank. A 7pt tracked eyebrow reads as subordinate to a 12pt
  title whatever colour either one is.
* **Contrast** carries legibility, so it rises as size falls. On a parchment background the
  usable contrast span between pure black and the 4.5:1 floor is only about 4:1, which is not
  enough for three ranks of colour; trying to encode rank in colour therefore spends the
  budget without buying much. Spending it on small text instead is what keeps a 7pt label
  readable once the artifact is scaled into a figure slot.

``emphasis`` promotes a role to the brand accent. It is one axis with one meaning -- this is
the thing the reader should look at first -- rather than a colour each family picks for its
own reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..scene import SceneText
from ..theme.folio import FolioTheme


class TextRole(str, Enum):
    """What a piece of text is for, never what it should look like."""

    # Frame
    DIAGRAM_TITLE = "diagram-title"
    DIAGRAM_SUBTITLE = "diagram-subtitle"
    REGION_LABEL = "region-label"
    LANE_LABEL = "lane-label"

    # Nodes and boxes
    NODE_EYEBROW = "node-eyebrow"
    NODE_TITLE = "node-title"
    NODE_META = "node-meta"
    KNOCKOUT = "knockout"

    # Relationships
    EDGE_LABEL = "edge-label"

    # Notation bodies
    NOTATION_MEMBER = "notation-member"
    NOTATION_TYPE = "notation-type"
    NOTATION_KEY = "notation-key"

    # Charts
    AXIS_LABEL = "axis-label"
    AXIS_TITLE = "axis-title"
    VALUE_LABEL = "value-label"
    VALUE_HERO = "value-hero"
    SERIES_KEY = "series-key"
    POINT_LABEL = "point-label"
    CAPTION = "caption"
    CAPTION_MONO = "caption-mono"
    SEGMENT_LABEL = "segment-label"
    HUB_CAPTION = "hub-caption"
    STEP_TITLE = "step-title"

    # Commentary
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


def resolve_text_style(
    role: TextRole,
    theme: FolioTheme,
    *,
    emphasis: str = "normal",
) -> TextStyle:
    """The look of one role, optionally promoted to the accent.

    ``emphasis="focal"`` swaps in the brand colour. Knockout text sits on a filled shape and
    keeps the page colour either way, since an accent on an accent disappears.
    """
    styles = {
        # --- Frame: large, so contrast can relax ---
        TextRole.DIAGRAM_TITLE: TextStyle(theme.serif, 24, theme.near_black, "middle"),
        TextRole.DIAGRAM_SUBTITLE: TextStyle(theme.serif, 11, theme.label, "middle"),
        TextRole.REGION_LABEL: TextStyle(theme.mono, 11, theme.label, tracking=0.08),
        TextRole.LANE_LABEL: TextStyle(theme.mono, 9, theme.olive, tracking=0.08),

        # --- Nodes: the title is the content, the rest is chrome ---
        TextRole.NODE_EYEBROW: TextStyle(theme.mono, 7, theme.olive, tracking=0.15),
        TextRole.NODE_TITLE: TextStyle(theme.serif, 12, theme.near_black, "middle", weight="500"),
        TextRole.NODE_META: TextStyle(theme.mono, 9, theme.olive, "middle"),
        TextRole.KNOCKOUT: TextStyle(theme.mono, 7, theme.parchment, "middle"),
        # --- Relationships: small, so contrast rises ---
        TextRole.EDGE_LABEL: TextStyle(theme.mono, 8, theme.olive, "middle"),

        # --- Notation: dense rows that must stay scannable ---
        TextRole.NOTATION_MEMBER: TextStyle(theme.mono, 8, theme.near_black),
        TextRole.NOTATION_TYPE: TextStyle(theme.mono, 8, theme.olive),
        TextRole.NOTATION_KEY: TextStyle(theme.mono, 7, theme.olive, tracking=0.08),

        # --- Charts: the value is the message, the scale is reference ---
        # Tick and axis readings are mono: they are numbers, and a monospaced column of digits
        # aligns. Axis titles and series names are prose, so they stay serif like the rest of the
        # editorial voice -- swapping them to mono silently widened nine diagrams.
        TextRole.AXIS_LABEL: TextStyle(theme.mono, 8, theme.olive),
        TextRole.AXIS_TITLE: TextStyle(theme.serif, 9, theme.olive),
        TextRole.VALUE_LABEL: TextStyle(theme.mono, 8, theme.near_black),
        TextRole.VALUE_HERO: TextStyle(theme.serif, 22, theme.near_black, "middle", weight="500"),
        TextRole.SERIES_KEY: TextStyle(theme.serif, 9, theme.olive),
        TextRole.POINT_LABEL: TextStyle(theme.serif, 8, theme.near_black),
        TextRole.CAPTION: TextStyle(theme.serif, 9, theme.olive),
        TextRole.CAPTION_MONO: TextStyle(theme.mono, 9, theme.olive),
        # A chart segment names a slice of the data rather than titling a box, so it carries no
        # extra weight.
        TextRole.SEGMENT_LABEL: TextStyle(theme.serif, 11, theme.near_black),
        # The flywheel hub states the compounding effect the ring produces: supporting prose
        # around which the stages turn, not a heading of its own.
        TextRole.HUB_CAPTION: TextStyle(theme.serif, 11, theme.olive, "middle"),
        # A numbered step in a side list names its stage without competing with the ring itself.
        TextRole.STEP_TITLE: TextStyle(theme.serif, 10, theme.near_black),

        # --- Commentary ---
        TextRole.ANNOTATION: TextStyle(theme.serif, 8, theme.near_black),
        TextRole.LEGEND: TextStyle(theme.mono, 9, theme.olive),
    }
    style = styles[role]
    if role is TextRole.KNOCKOUT:
        # Knockout only reads on a filled shape, and only the focal mark is filled. Elsewhere the
        # mark is an outline on the page colour, where page-coloured text disappears -- the
        # quality gate caught exactly that at 1.06:1.
        return style if emphasis == "focal" else TextStyle(
            style.family, style.size, theme.near_black, style.anchor, style.tracking, style.weight
        )
    if emphasis == "focal":
        return TextStyle(style.family, style.size, theme.brand, style.anchor, style.tracking, style.weight)
    return style


def role_text(
    text: str,
    x: int,
    y: int,
    role: TextRole,
    theme: FolioTheme,
    *,
    emphasis: str = "normal",
    anchor: str | None = None,
    size: float | None = None,
    tracking: float | None = None,
    klass: str | None = None,
) -> SceneText:
    """Build a ``SceneText`` from a role so no call site has to name a colour.

    ``anchor``, ``size`` and ``tracking`` stay overridable because the same role legitimately
    appears left-, centre- and right-aligned, and a few charts need a tighter size to fit a
    column. Colour is deliberately not overridable: that is the decision this module exists to
    hold, and letting a caller pass one is how the table stopped describing the output.
    """
    style = resolve_text_style(role, theme, emphasis=emphasis)
    return SceneText(
        text,
        x,
        y,
        style.color,
        style.size if size is None else size,
        style.family,
        style.anchor if anchor is None else anchor,
        style.tracking if tracking is None else tracking,
        style.weight,
        klass=klass,
    )
