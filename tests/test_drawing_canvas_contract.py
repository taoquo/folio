"""Cross-family canvas contract tests.

Every payload declares the same 960-unit stage width, and every family exposes `height` as a
bounded knob on the 4-unit grid. This locks the shared contract so a new family cannot quietly
reintroduce its own floor.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.canvas_contract import (
    CANVAS_WIDTH,
    CHART_CANVAS,
    GRAPH_CANVAS,
    NOTATION_CANVAS,
    CanvasBand,
    canvas_issues,
)
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.validation import DrawingCompilationError

GRAPH_KINDS = (
    "architecture", "flowchart", "state-machine", "swimlane", "tree", "layer-stack",
    "timeline", "quadrant", "venn", "pyramid", "org-chart", "loop-flywheel",
)
CHART_KINDS = ("bar-chart", "line-chart", "donut-chart", "candlestick", "waterfall", "scatter", "gantt", "heatmap")
NOTATION_KINDS = ("sequence", "uml-class", "er-diagram")
# Flowchart fits the stage to its widest row, so its scene width is intentionally narrower.
ADAPTIVE_WIDTH_KINDS = frozenset({"flowchart"})
BANDS = {"graph": GRAPH_CANVAS, "chart": CHART_CANVAS, "notation": NOTATION_CANVAS}


def band_schema(band: CanvasBand) -> dict:
    """The JSON Schema fragment a published schema must publish for this band."""
    return {"type": "integer", "minimum": band.minimum, "maximum": band.poster_maximum, "multipleOf": 4}


def showcase_fixture(kind: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / "showcase" / f"{kind}.json").read_text(encoding="utf-8"))


class CanvasBandTests(TestCase):
    def test_every_band_default_sits_inside_the_band(self) -> None:
        for name, band in BANDS.items():
            with self.subTest(band=name):
                self.assertTrue(band.accepts(band.default))
                self.assertTrue(band.accepts(band.minimum))
                self.assertTrue(band.accepts(band.maximum))

    def test_band_rejects_non_integers_and_off_grid_values(self) -> None:
        for name, band in BANDS.items():
            for value in (band.minimum - 4, band.maximum + 4, band.minimum + 2, float(band.default), True, None, "540"):
                with self.subTest(band=name, value=value):
                    self.assertFalse(band.accepts(value))

    def test_resolve_falls_back_without_masking_the_diagnostic(self) -> None:
        payload = {"height": 4000}
        self.assertEqual(GRAPH_CANVAS.default, GRAPH_CANVAS.resolve(payload))
        self.assertEqual(640, GRAPH_CANVAS.resolve(payload, 640))
        issues = canvas_issues(payload, kind="tree", band=GRAPH_CANVAS)
        # A height past the figure ceiling is reported with the mode that would accept it,
        # because "too tall" and "too tall for a figure" call for different fixes.
        self.assertEqual(2, len(issues))
        self.assertIn("must be a multiple of 4 from 500 to 800", issues[0])
        self.assertIn('"canvas": "poster"', issues[1])

    def test_out_of_band_height_only_names_poster_when_poster_would_accept_it(self) -> None:
        # Off-grid and below-floor heights are wrong in either mode, so pointing at poster
        # would send an author to change modes when they need to change the number.
        for height in (542, 400, 4001):
            with self.subTest(height=height):
                issues = canvas_issues({"height": height}, kind="tree", band=GRAPH_CANVAS)
                self.assertEqual(1, len(issues))
        # In poster mode the ceiling has already moved, so there is nothing left to suggest.
        issues = canvas_issues({"height": 5000, "canvas": "poster"}, kind="tree", band=GRAPH_CANVAS)
        self.assertEqual(1, len(issues))
        self.assertIn("from 500 to 4000", issues[0])

    def test_canvas_issues_reports_width_and_height_independently(self) -> None:
        self.assertEqual([], canvas_issues({}, kind="tree", band=GRAPH_CANVAS))
        self.assertEqual(2, len(canvas_issues({"width": 940, "height": 542}, kind="tree", band=GRAPH_CANVAS)))
        issues = canvas_issues({"width": 940}, kind="tree", band=GRAPH_CANVAS)
        self.assertEqual(1, len(issues))
        self.assertIn("canvas width", issues[0])


class GraphCanvasContractTests(TestCase):
    def test_graph_canvas_height_is_a_real_knob(self) -> None:
        for kind in GRAPH_KINDS:
            for height in (GRAPH_CANVAS.minimum, GRAPH_CANVAS.default, 640, GRAPH_CANVAS.maximum):
                with self.subTest(kind=kind, height=height):
                    payload = showcase_fixture(kind)
                    payload.update(width=CANVAS_WIDTH, height=height)
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                    if kind in ADAPTIVE_WIDTH_KINDS:
                        # Flowchart only grows the stage, so a taller canvas must never shrink it.
                        self.assertGreaterEqual(result.scene.height, height)
                        self.assertLessEqual(result.scene.width, CANVAS_WIDTH)
                    else:
                        self.assertEqual((CANVAS_WIDTH, height), (result.scene.width, result.scene.height))

    def test_graph_band_holds_for_every_published_fixture_shape(self) -> None:
        """The band is a promise about geometry, not only about the showcase fixture."""
        heights = (GRAPH_CANVAS.minimum, GRAPH_CANVAS.default, GRAPH_CANVAS.maximum)
        for kind in GRAPH_KINDS:
            for directory in ("v3", "v5", "minimal"):
                path = ROOT / "references" / "fixtures" / directory / f"{kind}.json"
                if not path.exists():
                    continue
                for height in heights:
                    with self.subTest(kind=kind, fixture=directory, height=height):
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        payload.update(width=CANVAS_WIDTH, height=height)
                        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                        self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])

    def test_loop_flywheel_ring_stays_inside_every_band_height(self) -> None:
        """Radial geometry is derived from the canvas, so no stage count can push the ring out."""
        from drawing.schematic import LOOP_STAGE_RADIUS, loop_ring_geometry

        payload = showcase_fixture("loop-flywheel")
        stages = payload["stages"]
        for height in range(GRAPH_CANVAS.minimum, GRAPH_CANVAS.maximum + 1, 4):
            center, radius = loop_ring_geometry(height)
            self.assertGreater(radius, 0)
            self.assertGreaterEqual(center - radius - LOOP_STAGE_RADIUS, 0)
            self.assertLessEqual(center + radius + LOOP_STAGE_RADIUS, height)
        for count in range(3, len(stages) + 1):
            for height in range(GRAPH_CANVAS.minimum, GRAPH_CANVAS.maximum + 1, 4):
                with self.subTest(stages=count, height=height):
                    candidate = dict(payload, stages=stages[:count], width=CANVAS_WIDTH, height=height)
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(candidate)
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])

    def test_out_of_band_graph_canvas_is_rejected(self) -> None:
        cases = (
            (CANVAS_WIDTH, GRAPH_CANVAS.minimum - 4, "height below minimum"),
            (CANVAS_WIDTH, GRAPH_CANVAS.maximum + 4, "height above maximum"),
            (CANVAS_WIDTH, GRAPH_CANVAS.default + 2, "height off the 4-unit grid"),
            (CANVAS_WIDTH - 20, GRAPH_CANVAS.default, "width is not 960"),
        )
        for kind in GRAPH_KINDS:
            for width, height, reason in cases:
                with self.subTest(kind=kind, reason=reason):
                    payload = showcase_fixture(kind)
                    payload.update(width=width, height=height)
                    with self.assertRaises(DrawingCompilationError) as context:
                        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertIn("canvas", str(context.exception))


class PublishedSchemaContractTests(TestCase):
    def _schema(self, name: str) -> dict:
        return json.loads((ROOT / "references" / "schemas" / name).read_text(encoding="utf-8"))

    def test_every_type_schema_pins_the_shared_width_and_its_family_band(self) -> None:
        expected = {
            **{kind: GRAPH_CANVAS for kind in GRAPH_KINDS},
            **{kind: CHART_CANVAS for kind in CHART_KINDS},
            **{kind: NOTATION_CANVAS for kind in NOTATION_KINDS},
        }
        for kind, band in expected.items():
            with self.subTest(kind=kind):
                properties = self._schema(f"types/{kind}.schema.json")["properties"]
                self.assertEqual({"const": CANVAS_WIDTH}, properties["width"])
                self.assertEqual(band_schema(band), properties["height"])

    def test_aggregate_payload_schema_shares_one_width_definition(self) -> None:
        defs = self._schema("drawing-payload-v3.schema.json")["$defs"]
        self.assertEqual({"const": CANVAS_WIDTH}, defs["canvas-width"])
        published = (
            ("graph-height", GRAPH_CANVAS),
            ("chart-height", CHART_CANVAS),
            ("notation-height", NOTATION_CANVAS),
        )
        for name, band in published:
            with self.subTest(definition=name):
                self.assertEqual(band_schema(band), defs[name])
        self.assertNotIn("dimension", defs)

    def test_plan_schemas_track_the_graph_band(self) -> None:
        for name in ("drawing-plan-v2.schema.json", "types/flowchart.schema.json"):
            with self.subTest(schema=name):
                properties = self._schema(name)["properties"]
                self.assertEqual({"const": CANVAS_WIDTH}, properties["width"])
                self.assertEqual(band_schema(GRAPH_CANVAS), properties["height"])

    def test_schemas_preserve_figure_limits_and_accept_poster_heights(self) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is installed by requirements-ci.txt")

        from drawing.schema_registry import list_schema_contracts

        aggregate = Draft202012Validator(self._schema("drawing-payload-v3.schema.json"))
        for contract in list_schema_contracts():
            payload = contract.load_minimal_payload()
            band = CHART_CANVAS if contract.kind in CHART_KINDS else NOTATION_CANVAS if contract.kind in NOTATION_KINDS else GRAPH_CANVAS
            validators = [Draft202012Validator(contract.load_schema())]
            if contract.kind not in {"architecture", "flowchart"}:
                validators.append(aggregate)
            for validator in validators:
                with self.subTest(kind=contract.kind, schema=validator.schema["title"]):
                    payload.pop("canvas", None)
                    payload["height"] = band.maximum + 4
                    self.assertTrue(list(validator.iter_errors(payload)))
                    payload["canvas"] = "poster"
                    self.assertFalse(list(validator.iter_errors(payload)))
                    payload["height"] = band.poster_maximum + 4
                    self.assertTrue(list(validator.iter_errors(payload)))
