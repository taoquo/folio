from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .base import SpacingGrammar

# `padding` is an ELK-style bracket string rather than a struct: the layout
# engine reads it verbatim. Scaling rewrites the four values in place.
_PADDING = re.compile(r"(top|left|bottom|right)=(\d+)")


def _grid(value: float, minimum: int = 4) -> int:
    """Round a scaled length onto the 4-unit grid the geometry contract uses."""
    return max(minimum, int(round(value / 4.0)) * 4)


# A node box holds three lines of type at fixed sizes: a 7-unit eyebrow at +20,
# a 12-unit title at +40 and a 9-unit meta at +56. The stage can shrink the
# gaps around a box but it cannot shrink the box past the type it must hold, so
# these floors are derived from that stack rather than from the 960 grid.
MIN_NODE_WIDTH = 96
MIN_NODE_HEIGHT = 64

# The diagram title's baseline is 40 units with a 20-unit type size, so 64 is
# the least frame that clears it. It is a floor for the same reason the node
# floors are: the title does not scale, so the frame above it cannot either.
MIN_FRAME_TOP = 64

# A region label's baseline sits 16 units under its boundary's top edge, and
# the label is 8-unit type. The padding above the first node therefore has to
# hold the label, or the label lands on the row it names: 20 units leaves the
# same 4 units of air the wording had before the stage could shrink it.
MIN_GROUP_PAD_TOP = 20

# A connector crosses the gap between two rows and its label -- 16 units of
# type -- lives in that gap. So does the group boundary that wraps the lower
# row, with its own padding. Both are type and neither scales, so the gap has to
# hold the label, the air around it, and that padding: 4 + 16 + 4 + 20.
# Reserving room is not the same as guaranteeing a place: the label placer still
# drops one that cannot sit beside its own line, and a plate that grows its rows
# further to make room would leave the aspect band the plate has to keep.
MIN_LAYER_GAP = 4 + 16 + 4 + MIN_GROUP_PAD_TOP

@dataclass(frozen=True)
class ArchitectureGeometryGrammar:
    grid: int = 4
    node_width: int = 176
    node_height: int = 72
    node_gap: int = 48
    layer_gap: int = 96
    edge_node_gap: int = 24
    edge_edge_gap: int = 18
    padding: str = "[top=80,left=96,bottom=72,right=96]"
    # The frame the rows are placed inside, measured in stage units. It is
    # chrome, not type: a 72-unit gutter is a margin at 960 and a fifth of the
    # canvas at 348, so it has to travel with the stage or the narrow
    # composition is mostly margin.
    frame_top: int = 92
    frame_bottom: int = 64
    frame_left: int = 72
    frame_right: int = 72
    # The pipeline composition keeps its own, slightly wider frame and its own
    # row pitch, both measured when the family was drawn. They are separate
    # fields rather than one shared frame because unifying them would move every
    # published 960-unit pipeline.
    pipeline_frame_left: int = 64
    pipeline_frame_right: int = 64
    pipeline_step: int = 148
    node_radius: int = 5
    group_radius: int = 10
    group_pad_x: int = 20
    group_pad_top: int = 24
    group_pad_bottom: int = 20
    arrow_size: int = 8
    size_tiers: tuple[tuple[str, int, int], ...] = (
        ("compact", 144, 64),
        ("regular", 176, 72),
        ("wide", 224, 80),
    )

    def scaled(self, scale: float) -> ArchitectureGeometryGrammar:
        """The same composition in less room.

        Chrome — padding, gaps, gutters, the node tiers — is measured in stage
        units and has to shrink with the stage. The type scale is not part of
        this object, and that asymmetry is the whole point: a drawing composed
        on a narrower stage keeps its 7 / 9 / 12-unit type, so the type grows
        relative to the stage and arrives larger in the column. The arrowhead
        stays at its authored size for the same reason a hairline stays a
        hairline: it is a mark, not a gutter.
        """
        if scale == 1:
            return self
        padding = _PADDING.sub(lambda m: f"{m.group(1)}={_grid(int(m.group(2)) * scale)}", self.padding)
        return replace(
            self,
            node_width=_grid(self.node_width * scale, MIN_NODE_WIDTH),
            node_height=_grid(self.node_height * scale, MIN_NODE_HEIGHT),
            node_gap=_grid(self.node_gap * scale),
            # A connector's label rides in this gap and does not scale.
            layer_gap=max(_grid(self.layer_gap * scale), MIN_LAYER_GAP),
            edge_node_gap=_grid(self.edge_node_gap * scale),
            edge_edge_gap=_grid(self.edge_edge_gap * scale),
            padding=padding,
            # The diagram title keeps its type size on every stage, so the top
            # frame cannot shrink past the space that title needs. Scaling it
            # freely is what put a band header inside the title at 350 units.
            frame_top=max(_grid(self.frame_top * scale), MIN_FRAME_TOP),
            frame_bottom=_grid(self.frame_bottom * scale),
            frame_left=_grid(self.frame_left * scale),
            frame_right=_grid(self.frame_right * scale),
            pipeline_frame_left=_grid(self.pipeline_frame_left * scale),
            pipeline_frame_right=_grid(self.pipeline_frame_right * scale),
            pipeline_step=_grid(self.pipeline_step * scale),
            node_radius=max(2, _grid(self.node_radius * scale, 2)),
            group_radius=max(2, _grid(self.group_radius * scale, 2)),
            group_pad_x=_grid(self.group_pad_x * scale),
            # The region label sits in this padding and does not scale, so the
            # padding cannot shrink past it.
            group_pad_top=max(_grid(self.group_pad_top * scale), MIN_GROUP_PAD_TOP),
            group_pad_bottom=_grid(self.group_pad_bottom * scale),
            size_tiers=tuple((name, _grid(w * scale, MIN_NODE_WIDTH), _grid(h * scale, MIN_NODE_HEIGHT))
                             for name, w, h in self.size_tiers),
        )


@dataclass(frozen=True)
class ArchitectureGrammar:
    geometry: ArchitectureGeometryGrammar = field(default_factory=ArchitectureGeometryGrammar)
    spacing: SpacingGrammar = field(default_factory=SpacingGrammar)
    composition_patterns: tuple[str, ...] = ("layered", "pipeline", "hub")
    axes: tuple[str, ...] = ("top-down", "left-right")
    node_archetypes: tuple[str, ...] = ("component", "datastore", "external", "cloud")
    edge_channels: tuple[str, ...] = ("primary-flow", "secondary-flow", "async-flow")
    emphasis_levels: tuple[str, ...] = ("focal", "normal", "background")
    region_treatments: tuple[str, ...] = ("layer-band", "soft-boundary", "trust-boundary", "phase-band", "none")
    pictograms: tuple[str, ...] = (
        "client", "gateway", "compute", "queue", "database", "cache",
        "storage", "cloud", "security", "observability", "network", "external-system",
    )

    def scaled(self, scale: float) -> ArchitectureGrammar:
        """This grammar composed in less room; only the geometry moves."""
        return replace(self, geometry=self.geometry.scaled(scale))


DEFAULT_ARCHITECTURE_GRAMMAR = ArchitectureGrammar()
