"""Scene-level checks added for the Web figure pipeline.

DG140 shape truth, DG141 legend collision, DG142 arrow entry distance. Each has
a positive and a negative case, because a check that never fires is not a check.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.scene import (  # noqa: E402
    ArrowGeometry,
    ResolvedScene,
    SceneBox,
    SceneEdge,
    SceneLegend,
    SceneNode,
    ScenePolyline,
    SceneStyle,
    SceneText,
)
from drawing.validation.geometry import validate_scene_geometry  # noqa: E402

STYLE = SceneStyle(fill="#FBF7F3", stroke="#E6DACD", stroke_width=1)
TITLE = SceneText(text="title", x=8, y=16, fill="#191514", size=12, family="serif")


def node(node_id: str, x: int, y: int, w: int = 176, h: int = 72) -> SceneNode:
    return SceneNode(id=node_id, box=SceneBox(x, y, w, h), style=STYLE, text_runs=())


def scene(**overrides) -> ResolvedScene:
    values = dict(
        width=960,
        height=500,
        background="#F6F0EA",
        title=TITLE,
        regions=(),
        edges=(),
        nodes=(),
        primitives=(),
    )
    values.update(overrides)
    return ResolvedScene(**values)


def codes(result) -> list[str]:
    return [item.code for item in result]


class ShapeTruthTests(unittest.TestCase):
    def test_a_para11elogram_with_equal_opposite_sides_passes(self) -> None:
        shape = ScenePolyline(
            id="p1",
            points=((100, 100), (180, 100), (200, 160), (120, 160), (100, 100)),
            style=STYLE,
            klass="parallelogram",
        )
        self.assertNotIn("DG140", codes(validate_scene_geometry(scene(primitives=(shape,)))))

    def test_a_skewed_parallelogram_is_reported(self) -> None:
        shape = ScenePolyline(
            id="p2",
            points=((100, 100), (180, 100), (200, 160), (100, 160), (100, 100)),
            style=STYLE,
            klass="parallelogram",
        )
        self.assertIn("DG140", codes(validate_scene_geometry(scene(primitives=(shape,)))))

    def test_an_unmarked_shape_is_left_alone(self) -> None:
        shape = ScenePolyline(
            id="free",
            points=((100, 100), (180, 100), (200, 160), (100, 160), (100, 100)),
            style=STYLE,
        )
        self.assertNotIn("DG140", codes(validate_scene_geometry(scene(primitives=(shape,)))))


class LegendCollisionTests(unittest.TestCase):
    def test_a_legend_that_overlaps_a_node_is_reported(self) -> None:
        legend = SceneLegend(box=SceneBox(100, 100, 200, 80), style=STYLE, title=TITLE, items=())
        result = validate_scene_geometry(scene(nodes=(node("a", 120, 110),), legend=legend))
        self.assertIn("DG141", codes(result))

    def test_a_legend_in_free_space_passes(self) -> None:
        legend = SceneLegend(box=SceneBox(700, 60, 200, 80), style=STYLE, title=TITLE, items=())
        result = validate_scene_geometry(scene(nodes=(node("a", 100, 300),), legend=legend))
        self.assertNotIn("DG141", codes(result))


class ArrowEntryTests(unittest.TestCase):
    def test_an_arrow_near_a_corner_is_flagged(self) -> None:
        target = node("target", 400, 200)
        edge = SceneEdge(
            id="edge",
            source="source",
            target="target",
            points=((360, 210), (400, 210)),
            style=STYLE,
            arrow=ArrowGeometry(points=((394, 206), (400, 210), (394, 214))),
            klass="primary",
        )
        result = validate_scene_geometry(scene(nodes=(node("source", 100, 200), target), edges=(edge,)))
        self.assertIn("DG142", codes(result))

    def test_an_arrow_at_the_mid_edge_passes(self) -> None:
        target = node("target", 400, 200)
        edge = SceneEdge(
            id="edge",
            source="source",
            target="target",
            points=((360, 236), (400, 236)),
            style=STYLE,
            arrow=ArrowGeometry(points=((394, 232), (400, 236), (394, 240))),
            klass="primary",
        )
        result = validate_scene_geometry(scene(nodes=(node("source", 100, 200), target), edges=(edge,)))
        self.assertNotIn("DG142", codes(result))


if __name__ == "__main__":
    unittest.main()
