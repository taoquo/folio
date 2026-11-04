"""The chrome of a banded graph, in stage units.

State machine and swimlane compose on a canvas they were authored at: node
boxes, row gaps, margins and lane gutters are all numbers measured against 960.
The type tiers are not -- a node title is 12 units wherever it is set -- so a
960-unit graph in a 350px column delivers that title at 4.4px.

This object is the same answer architecture gave its own geometry: the host
names a stage, the family scales the chrome into it and leaves the type alone.
``scaled(1.0)`` returns the object itself, so the authored 960 path is not
"scaled by one" arithmetically but *not run through the scaling code at all* --
the published artifacts cannot drift by a rounding step.

Three kinds of number live here, and the comments say which is which:

* chrome -- scales with the stage, on the 4-unit grid;
* type -- baseline, insets, label lanes, arrowheads: never scales;
* floors -- the least box that still holds the type. They are derived from
  ``measure_text`` at call time where the text is known, and are constants
  here only where the value is a fixed typographic relationship.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..stage import StageSpec
from ..stage import current as current_stage

BASE_NODE_SIZES: tuple[tuple[str, int, int], ...] = (
    ("initial", 16, 16),
    ("final", 20, 20),
    ("choice", 56, 56),
    ("decision", 88, 72),
    ("terminal", 128, 48),
    ("data", 144, 56),
    ("leaf", 128, 48),
    ("layer", 720, 56),
)
DEFAULT_NODE_SIZE = (144, 64)
MARK_ARCHETYPES = frozenset({"initial", "final"})


def _grid(value: float | int, minimum: int = 4) -> int:
    return max(minimum, int(round(float(value) / 4) * 4))


@dataclass(frozen=True)
class GraphGeometry:
    """Every number the banded layout is allowed to draw with."""

    scale: float = 1.0
    node_sizes: tuple[tuple[str, int, int], ...] = BASE_NODE_SIZES
    default_node: tuple[int, int] = DEFAULT_NODE_SIZE

    # Chrome: rows, margins and the feedback band.
    node_gap: int = 48
    dense_node_gap: int = 32
    dense_threshold: int = 8
    band_top: int = 96
    feedback_band_top: int = 176
    band_bottom: int = 48
    top_down_origin: int = 72
    top_down_bias: int = 16
    side_margin: int = 24
    node_radius: int = 6

    # Chrome: swimlane lanes.
    lane_top: int = 80
    lane_bottom: int = 40
    lane_left: int = 72
    lane_right: int = 40
    lane_step_left: int = 136
    lane_step_pad: int = 168
    lane_step_left_dense: int = 92
    lane_step_pad_dense: int = 92
    lane_top_down_origin: int = 112
    lane_top_down_bottom: int = 112
    lane_box_x: int = 72
    lane_box_width_pad: int = 112
    lane_label_x: int = 84
    lane_label_offset: int = 20
    lane_top_down_label_y: int = 92
    lane_pad: int = 8
    lane_header: int = 28
    lane_node_width: int = 128
    lane_node_height: int = 56
    lane_decision_width: int = 88
    lane_decision_height: int = 72
    lane_dense_width: int = 56
    lane_dense_height: int = 48
    lane_dense_decision_width: int = 72
    lane_dense_decision_height: int = 60

    # Type: the title block, the label lanes and the arrowheads do not scale.
    title_baseline: int = 40
    title_clearance: int = 64
    title_wrap_inset: int = 24
    subtitle_inset: int = 8
    subtitle_pitch: int = 12
    fan_pitch: int = 16
    arrow_size: int = 8
    edge_label_size: float = 9
    label_lane_offset: int = 40
    label_lane_pitch: int = 12
    label_lane_margin: int = 24

    # Floors derived from the type scale.
    node_width_floor: int = 96
    node_height_floor: int = 48
    node_subtitle_height: int = 64
    mark_width_floor: int = 12
    mark_height_floor: int = 16
    lane_node_width_floor: int = 84
    lane_node_height_floor: int = 48
    min_gap: int = 8
    min_row_gap: int = 32
    min_side_margin: int = 8

    @property
    def is_default(self) -> bool:
        return self.scale == 1.0

    @property
    def approach_min(self) -> int:
        """The shortest run into a face that still reads as an arrow.

        The arrowhead is type, so it does not scale with the stage; the row gaps
        do. A lane clamped to the target face leaves the tip on a corner, so the
        approach is held to a whole arrowhead's depth regardless of the stage.
        """
        return self.arrow_size * 2

    def scaled(self, scale: float) -> GraphGeometry:
        """The same geometry composed on a stage ``scale`` times as wide."""
        if scale == 1.0:
            return self

        def chrome(value: int, floor: int = 4) -> int:
            return max(int(round(value * scale / 4) * 4), floor)

        node_sizes = tuple(
            (archetype, *_scaled_node(archetype, width, height, scale, self))
            for archetype, width, height in self.node_sizes
        )
        return replace(
            self,
            scale=scale,
            node_sizes=node_sizes,
            default_node=_scaled_node("default", *self.default_node, scale, self),
            node_gap=chrome(self.node_gap, self.min_gap),
            dense_node_gap=chrome(self.dense_node_gap, self.min_gap),
            band_top=chrome(self.band_top, self.title_clearance),
            feedback_band_top=chrome(self.feedback_band_top, self.title_clearance),
            band_bottom=chrome(self.band_bottom, self.min_side_margin),
            top_down_origin=chrome(self.top_down_origin, self.title_clearance),
            top_down_bias=chrome(self.top_down_bias, 4),
            side_margin=chrome(self.side_margin, self.min_side_margin),
            node_radius=chrome(self.node_radius, 4),
            lane_top=chrome(self.lane_top, self.title_clearance),
            lane_bottom=chrome(self.lane_bottom, self.min_side_margin),
            lane_left=chrome(self.lane_left, self.min_side_margin),
            lane_right=chrome(self.lane_right, self.min_side_margin),
            lane_step_left=chrome(self.lane_step_left, self.lane_pad + self.min_side_margin),
            lane_step_pad=chrome(self.lane_step_pad, self.lane_pad + self.min_side_margin),
            lane_step_left_dense=chrome(self.lane_step_left_dense, self.lane_pad + 4),
            lane_step_pad_dense=chrome(self.lane_step_pad_dense, self.lane_pad + 4),
            lane_top_down_origin=chrome(self.lane_top_down_origin, self.title_clearance),
            lane_top_down_bottom=chrome(self.lane_top_down_bottom, self.min_side_margin),
            lane_box_x=chrome(self.lane_box_x, self.min_side_margin),
            lane_box_width_pad=chrome(self.lane_box_width_pad, self.lane_pad * 2),
            lane_label_x=chrome(self.lane_label_x, self.min_side_margin),
            lane_label_offset=chrome(self.lane_label_offset, self.lane_pad),
            lane_top_down_label_y=chrome(self.lane_top_down_label_y, self.title_clearance),
            lane_pad=chrome(self.lane_pad, 4),
            lane_header=chrome(self.lane_header, self.lane_pad + 24),
            lane_node_width=chrome(self.lane_node_width, self.lane_node_width_floor),
            lane_node_height=chrome(self.lane_node_height, self.lane_node_height_floor),
            lane_decision_width=chrome(self.lane_decision_width, self.lane_node_width_floor),
            lane_decision_height=chrome(self.lane_decision_height, self.lane_node_height_floor),
        )

    def node_size(self, archetype: str) -> tuple[int, int]:
        for name, width, height in self.node_sizes:
            if name == archetype:
                return width, height
        return self.default_node


def _scaled_node(
    archetype: str,
    width: int,
    height: int,
    scale: float,
    geometry: GraphGeometry,
) -> tuple[int, int]:
    scaled_width = int(round(width * scale / 4) * 4)
    scaled_height = int(round(height * scale / 4) * 4)
    if archetype in MARK_ARCHETYPES:
        return (
            max(scaled_width, geometry.mark_width_floor),
            max(scaled_height, geometry.mark_height_floor),
        )
    return (
        max(scaled_width, geometry.node_width_floor),
        max(scaled_height, geometry.node_height_floor),
    )


DEFAULT_GRAPH_GEOMETRY = GraphGeometry()


def graph_geometry_for_stage(stage: StageSpec | None = None) -> GraphGeometry:
    stage = stage or current_stage()
    return DEFAULT_GRAPH_GEOMETRY if stage.is_default else DEFAULT_GRAPH_GEOMETRY.scaled(stage.scale)
