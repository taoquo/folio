"""Canvas modes: a figure keeps the editorial budget, a poster grows to fit its content.

The numbers in these tests are measurements, not preferences. `MIN_ROW_PITCH` and the
capacity formula were read off the layout engine by growing an architecture payload one
row at a time at ten different heights until it reported an overlap; the table in
`test_capacity_matches_the_measured_layout` is that measurement. If the layout's spacing
changes, this test is the thing that should fail first.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from drawing.canvas_contract import (  # noqa: E402
    CANVAS_MODES,
    GRAPH_CANVAS,
    NODES_PER_ROW,
    canvas_mode,
    height_for_row_capacity,
    height_for_rows,
    rows_for_height,
)
from drawing.compiler import DEFAULT_COMPILER_REGISTRY  # noqa: E402
from drawing.models import InformationBudget  # noqa: E402
from drawing.output import placement_advisory  # noqa: E402
from drawing.validation.models import DrawingCompilationError  # noqa: E402

# Rows placed without overlap at each height, measured against the layout engine.
MEASURED_CAPACITY = (
    (500, 4), (540, 5), (600, 6), (700, 7), (800, 8),
    (1000, 11), (1400, 17), (1800, 22), (2400, 31), (3000, 39),
)


def architecture(rows: int, *, canvas: str | None = None, height: int | None = None, per_row: int = NODES_PER_ROW) -> dict:
    layers = [{"id": f"L{index}", "label": f"Tier {index}"} for index in range(rows)]
    nodes = [
        {"id": f"n{index * per_row + offset}", "kind": "service", "label": f"Node {index * per_row + offset}", "layer": f"L{index}"}
        for index in range(rows)
        for offset in range(per_row)
    ]
    edges = [
        {"source": f"n{index * per_row + offset}", "target": f"n{(index + 1) * per_row + offset}", "kind": "primary"}
        for index in range(rows - 1)
        for offset in range(per_row)
    ]
    payload = {
        "schema_version": "3.0", "kind": "architecture", "title": f"{rows * per_row} nodes",
        "layout": "horizontal-layers", "layers": layers, "nodes": nodes, "edges": edges,
    }
    if canvas is not None:
        payload["canvas"] = canvas
    if height is not None:
        payload["height"] = height
    return payload


class CanvasModeTests(unittest.TestCase):
    def test_figure_is_the_default_and_keeps_the_editorial_budget(self) -> None:
        self.assertEqual("figure", canvas_mode({}))
        self.assertEqual(9, InformationBudget.for_canvas(540).max_nodes)
        # Extra air does not buy a figure more nodes: the budget is a claim about what
        # belongs in a figure, not about how much room is left.
        self.assertEqual(9, InformationBudget.for_canvas(800, "figure").max_nodes)

    def test_unknown_mode_falls_back_rather_than_breaking_layout_math(self) -> None:
        self.assertEqual("figure", canvas_mode({"canvas": "enormous"}))
        self.assertIn("figure", CANVAS_MODES)
        self.assertIn("poster", CANVAS_MODES)

    def test_capacity_matches_the_measured_layout(self) -> None:
        for height, rows in MEASURED_CAPACITY:
            with self.subTest(height=height):
                self.assertEqual(rows, rows_for_height(height))
                self.assertEqual(rows * NODES_PER_ROW, InformationBudget.for_canvas(height, "poster").max_nodes)

    def test_height_for_rows_is_the_inverse_and_lands_on_the_grid(self) -> None:
        for rows in range(1, 40):
            with self.subTest(rows=rows):
                height = height_for_rows(rows)
                self.assertEqual(0, height % 4, "canvas heights stay on the 4-unit grid")
                self.assertGreaterEqual(rows_for_height(height), rows)

    def test_poster_raises_the_ceiling_but_never_the_floor(self) -> None:
        # The floor is layout math -- below it label rings collide in either mode.
        self.assertFalse(GRAPH_CANVAS.accepts(496, "poster"))
        self.assertFalse(GRAPH_CANVAS.accepts(1800, "figure"))
        self.assertTrue(GRAPH_CANVAS.accepts(1800, "poster"))

    def test_width_is_pinned_in_both_modes(self) -> None:
        for mode in CANVAS_MODES:
            with self.subTest(mode=mode):
                payload = architecture(2, canvas=mode)
                payload["width"] = 1200
                with self.assertRaises(DrawingCompilationError) as caught:
                    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertIn("width must be exactly 960", str(caught.exception))


class PosterCompilationTests(unittest.TestCase):
    def test_figure_still_fails_closed_past_nine_nodes(self) -> None:
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(2))
        message = str(caught.exception)
        self.assertIn("DG002", message)
        # The remedy travels with the error, so the ceiling is discoverable at the point of use.
        self.assertIn("poster", message)

    def test_poster_places_what_a_figure_refuses(self) -> None:
        for rows in (2, 4, 8, 12, 20):
            with self.subTest(rows=rows):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(rows, canvas="poster"))
                self.assertEqual(rows * NODES_PER_ROW, len([n for n in result.plan.nodes]))

    def test_poster_derives_a_height_that_holds_its_rows(self) -> None:
        for rows in (2, 6, 12, 20):
            with self.subTest(rows=rows):
                scene = DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(rows, canvas="poster")).scene
                self.assertGreaterEqual(rows_for_height(scene.height), rows)
                self.assertEqual(960, scene.width, "width never grows")

    def test_an_explicit_poster_height_is_honoured(self) -> None:
        scene = DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(4, canvas="poster", height=1600)).scene
        self.assertEqual(1600, scene.height)

    def test_poster_still_fails_closed_past_its_own_capacity(self) -> None:
        # A short poster is still a bounded canvas; the number moves, failing closed does not.
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(8, canvas="poster", height=540))
        message = str(caught.exception)
        self.assertIn("DG002", message)
        self.assertIn("raise height", message)

    def test_derived_poster_height_cannot_bypass_the_canvas_ceiling(self) -> None:
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(60, canvas="poster"))
        self.assertIn("exceeds poster maximum 4000", str(caught.exception))

    def test_tall_figure_reports_the_poster_remedy(self) -> None:
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(1, height=1000))
        self.assertIn('canvas": "poster', str(caught.exception))

    def test_row_width_is_unchanged_by_mode(self) -> None:
        # Five across is the width constraint, and width is what both modes hold fixed.
        with self.assertRaises(DrawingCompilationError):
            DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(1, canvas="poster", per_row=6))

    def test_poster_plan_round_trip_and_auto_height(self) -> None:
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(12, canvas="poster"))
        import json

        payload = json.loads(json.dumps(result.plan.to_dict()))
        payload.pop("height")
        restored = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertEqual("poster", restored.plan.canvas)
        self.assertEqual(1020, restored.scene.height)
        self.assertEqual(60, len(restored.plan.nodes))
        self.assertIn("DG203", {item.code for item in restored.diagnostics})

    def test_direct_dataclass_cannot_bypass_the_canvas_limit(self) -> None:
        from dataclasses import replace

        from drawing.pipeline import compile_drawing_plan

        result = DEFAULT_COMPILER_REGISTRY.compile_payload(architecture(2, canvas="poster"))
        with self.assertRaises(DrawingCompilationError) as caught:
            compile_drawing_plan(replace(result.plan, height=5000))
        self.assertIn("DG044", str(caught.exception))


class PlacementAdvisoryTests(unittest.TestCase):
    def test_a_figure_sized_canvas_embeds_without_comment(self) -> None:
        self.assertIsNone(placement_advisory(960, 540, 174, 123))

    def test_a_poster_reports_how_far_it_overflows_a_slot(self) -> None:
        advisory = placement_advisory(960, 1596, 174, 123)
        self.assertIsNotNone(advisory)
        self.assertIn("split the diagram", advisory)

    def test_degenerate_dimensions_do_not_raise(self) -> None:
        self.assertIsNone(placement_advisory(0, 540, 174, 123))
        self.assertIsNone(placement_advisory(960, 540, 0, 0))


class ElasticRowCapacityTests(unittest.TestCase):
    """Chart rows compress to fit, so their ceiling protects density rather than placement."""

    def _grow(self, kind: str, field: str, count: int, *, height: int | None = None, poster: bool = False) -> dict:
        from drawing.schema_registry import schema_contract

        base = dict(schema_contract(kind).load_canonical_payload())
        items = list(base[field])
        template = items[-1]
        for index in range(count - len(items)):
            clone = dict(template)
            clone["id"] = f"{template['id']}_x{index}"
            if isinstance(clone.get("label"), str):
                clone["label"] = f"{template['label']} {index}"
            items.append(clone)
        base[field] = items
        if height is not None:
            base["height"] = height
        if poster:
            base["canvas"] = "poster"
        return base

    def test_row_capacity_holds_density_constant(self) -> None:
        from drawing.canvas_contract import row_capacity

        self.assertEqual(10, row_capacity({"height": 1600}, figure_ceiling=10))
        # 540 is the chart default, so a poster twice as tall carries twice the rows.
        self.assertEqual(20, row_capacity({"height": 1080, "canvas": "poster"}, figure_ceiling=10))
        self.assertEqual(1080, height_for_row_capacity(20, figure_ceiling=10))

    def test_figure_charts_keep_their_editorial_ceiling(self) -> None:
        for kind, field in (("gantt", "tasks"), ("heatmap", "rows")):
            with self.subTest(kind=kind):
                DEFAULT_COMPILER_REGISTRY.compile_payload(self._grow(kind, field, 10))
                with self.assertRaises(DrawingCompilationError) as caught:
                    DEFAULT_COMPILER_REGISTRY.compile_payload(self._grow(kind, field, 14))
                self.assertIn("poster", str(caught.exception))

    def test_poster_charts_scale_rows_with_the_canvas(self) -> None:
        for kind, field in (("gantt", "tasks"), ("heatmap", "rows")):
            for count, height in ((20, 1080), (40, 2160)):
                with self.subTest(kind=kind, count=count):
                    DEFAULT_COMPILER_REGISTRY.compile_payload(
                        self._grow(kind, field, count, height=height, poster=True)
                    )

    def test_poster_charts_derive_height_when_it_is_omitted(self) -> None:
        for kind, field in (("gantt", "tasks"), ("heatmap", "rows")):
            with self.subTest(kind=kind):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(
                    self._grow(kind, field, 20, poster=True)
                )
                self.assertEqual(1080, result.scene.height)

    def test_derived_chart_height_respects_the_poster_ceiling(self) -> None:
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(
                self._grow("gantt", "tasks", 45, poster=True)
            )
        self.assertIn("2400", str(caught.exception))

    def test_poster_charts_still_refuse_to_crowd(self) -> None:
        # Two rows past what the canvas pays for is still refused, so density is protected
        # in poster mode rather than abandoned.
        with self.assertRaises(DrawingCompilationError):
            DEFAULT_COMPILER_REGISTRY.compile_payload(
                self._grow("gantt", "tasks", 40, height=1080, poster=True)
            )


if __name__ == "__main__":
    unittest.main()
