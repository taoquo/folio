import json
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.hosting import accessible_data
from drawing.scene import SceneText
from drawing.validation import DrawingCompilationError
from diagram_export import export_pdf, export_png
from renderers.svg import render_svg


def fixture(kind: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / "v3" / f"{kind}.json").read_text(encoding="utf-8"))


def minimal_fixture(kind: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / "minimal" / f"{kind}.json").read_text(encoding="utf-8"))


def showcase_fixture(kind: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / "showcase" / f"{kind}.json").read_text(encoding="utf-8"))


def scene_texts(payload: dict) -> list[str]:
    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    return [item.text for item in result.scene.primitives if isinstance(item, SceneText)]


class DrawingDataVizV4RegressionTests(TestCase):
    def test_maintained_v42_feature_fixtures_match_detailed_schemas(self) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is installed by requirements-ci.txt")

        for path in sorted((ROOT / "references" / "fixtures" / "v4").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "references" / "schemas" / "types" / f"{payload['kind']}.schema.json").read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                self.assertEqual([], list(Draft202012Validator(schema).iter_errors(payload)))
                self.assertEqual(payload["kind"], DEFAULT_COMPILER_REGISTRY.compile_payload(payload).kind)

    def test_v42_feature_fixtures_cover_three_profiles_and_formats(self) -> None:
        with TemporaryDirectory() as temp:
            output = Path(temp)
            count = 0
            for path in sorted((ROOT / "references" / "fixtures" / "v4").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                for profile in ("artifact", "embed", "page-preview"):
                    with self.subTest(path=path.name, profile=profile):
                        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile)
                        svg = output / f"{path.stem}-{profile}.svg"
                        png = output / f"{path.stem}-{profile}.png"
                        pdf = output / f"{path.stem}-{profile}.pdf"
                        svg.write_text(render_svg(result.scene, profile), encoding="utf-8")
                        export_png(svg, png, profile=profile, title=result.plan.title, language=result.plan.language)
                        export_pdf(svg, pdf, result.plan.title, result.plan.language, profile)
                        self.assertTrue(all(item.stat().st_size > 100 for item in (svg, png, pdf)))
                        count += 3
            fixture_count = len(list((ROOT / "references" / "fixtures" / "v4").glob("*.json")))
            self.assertEqual(fixture_count * 3 * 3, count)

    def test_accessible_table_uses_effective_missing_policy_and_bar_order(self) -> None:
        line = fixture("line-chart")
        line["series"][0]["values"][1] = None
        line["missing_policy"] = "zero"
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(line)
        table = accessible_data(result)

        self.assertEqual(0.0, result.plan.series[0]["values"][1])
        self.assertEqual("0", table.rows[1][1])

        bar = fixture("bar-chart")
        bar["order"] = list(reversed(bar["categories"]))
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(bar)
        table = accessible_data(result)
        self.assertEqual(result.plan.categories[0], table.rows[0][0])
        self.assertEqual(str(result.plan.series[0]["values"][0]), table.rows[0][1])

    def test_line_axis_labels_use_exact_point_positions(self) -> None:
        payload = fixture("line-chart")
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        labels = {
            item.text: item.x
            for item in result.scene.primitives
            if isinstance(item, SceneText) and item.text in payload["categories"]
        }

        self.assertEqual(dict(zip(result.plan.categories, result.layout.x_positions)), labels)

    def test_line_categories_are_unique_and_point_ids_survive_reorder(self) -> None:
        payload = fixture("line-chart")
        duplicate = deepcopy(payload)
        duplicate["categories"][1] = duplicate["categories"][0]
        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(duplicate)
        self.assertIn("LC011", {item.code for item in context.exception.diagnostics})

        first = deepcopy(payload)
        first["categories"] = ["A", "B", "C", "D", "E"]
        second = deepcopy(first)
        order = [2, 0, 4, 1, 3]
        second["categories"] = [first["categories"][index] for index in order]
        for index, series in enumerate(second["series"]):
            series["values"] = [first["series"][index]["values"][source] for source in order]

        left = DEFAULT_COMPILER_REGISTRY.compile_payload(first)
        right = DEFAULT_COMPILER_REGISTRY.compile_payload(second)
        self.assertEqual({item["id"] for item in left.semantic.marks}, {item["id"] for item in right.semantic.marks})

    def test_negative_bar_label_is_attached_to_negative_endpoint(self) -> None:
        payload = fixture("bar-chart")
        payload.update(categories=["Loss"], series=[{"id": "s", "label": "Series", "values": [-50]}])
        payload.pop("focus_series", None)
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        box = next(iter(result.layout.marks.values()))
        label = next(item for item in result.scene.primitives if isinstance(item, SceneText) and item.text == "-50 types")

        self.assertGreater(label.y, box.y + box.h)
        self.assertLessEqual(label.y, result.layout.plot.y + result.layout.plot.h)

    def test_data_chart_canvas_contract_matches_detailed_schema(self) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is installed by requirements-ci.txt")

        for kind in ("bar-chart", "line-chart", "donut-chart", "candlestick", "waterfall"):
            schema = json.loads((ROOT / "references" / "schemas" / "types" / f"{kind}.schema.json").read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            for width, height, reason in ((320, 240, "both out of range"), (960, 396, "height below minimum"), (960, 724, "height above maximum"), (960, 542, "height off the 4-unit grid"), (940, 540, "width is not 960")):
                with self.subTest(kind=kind, reason=reason):
                    payload = fixture(kind)
                    payload.update(width=width, height=height)
                    self.assertTrue(list(validator.iter_errors(payload)))
                    with self.assertRaises(DrawingCompilationError) as context:
                        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertIn("canvas", str(context.exception))
            for height in (400, 480, 640, 720):
                with self.subTest(kind=kind, height=height):
                    payload = fixture(kind)
                    payload.update(width=960, height=height)
                    self.assertEqual(list(validator.iter_errors(payload)), [])

    def test_bounded_canvas_height_is_a_real_knob(self) -> None:
        for kind in ("bar-chart", "line-chart", "donut-chart", "candlestick", "waterfall", "scatter", "gantt", "heatmap"):
            plot_heights = []
            for height in (400, 540, 720):
                with self.subTest(kind=kind, height=height):
                    payload = minimal_fixture(kind)
                    payload["height"] = height
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertEqual(result.scene.height, height)
                    self.assertEqual(result.scene.width, 960)
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                    plot_heights.append(result.layout.plot.h)
            with self.subTest(kind=kind):
                # The donut ring caps its radius at the VQ104 accent budget, so growth can plateau,
                # but a taller canvas must never shrink the plot band.
                self.assertEqual(sorted(plot_heights), plot_heights)
                self.assertGreater(len(set(plot_heights)), 1)

    def test_notation_canvas_height_is_a_real_knob(self) -> None:
        for kind, heights in (("sequence", (480, 540, 800)), ("uml-class", (560, 640, 800)), ("er-diagram", (560, 640, 800))):
            floors = []
            for height in heights:
                with self.subTest(kind=kind, height=height):
                    payload = showcase_fixture(kind)
                    payload["height"] = height
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertEqual(result.scene.height, height)
                    self.assertEqual(result.scene.width, 960)
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                    # Sequence spends the extra height on the message band, box notations on the grid.
                    if kind == "sequence":
                        floors.append(max(route[-1][1] for route in result.layout.relations.values()))
                    else:
                        floors.append(max(box.y + box.h for box in result.layout.boxes.values()))
            with self.subTest(kind=kind):
                self.assertEqual(sorted(set(floors)), floors)
                self.assertEqual(len(set(floors)), len(floors))

    def test_out_of_range_notation_height_is_rejected(self) -> None:
        for kind in ("sequence", "uml-class", "er-diagram"):
            for height in (476, 804, 641):
                with self.subTest(kind=kind, height=height):
                    payload = showcase_fixture(kind)
                    payload["height"] = height
                    with self.assertRaises(DrawingCompilationError) as context:
                        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertIn("canvas height", str(context.exception))

    def test_default_canvas_geometry_is_unchanged(self) -> None:
        expected = {
            "bar-chart": (100, 80, 720, 340), "line-chart": (100, 80, 720, 340),
            "candlestick": (100, 80, 720, 340), "waterfall": (100, 80, 720, 340),
            "scatter": (104, 88, 656, 344), "gantt": (232, 104, 608, 356),
            "heatmap": (232, 112, 560, 340),
        }
        for kind, box in expected.items():
            with self.subTest(kind=kind):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(minimal_fixture(kind))
                plot = result.layout.plot
                self.assertEqual((plot.x, plot.y, plot.w, plot.h), box)

    def test_waterfall_invalid_numeric_fields_keep_specific_diagnostics(self) -> None:
        for field, value, code in (("start", None, "WF001"), ("tolerance", "bad", "WF005")):
            payload = fixture("waterfall")
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(DrawingCompilationError) as context:
                DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            self.assertIn(code, {item.code for item in context.exception.diagnostics})
            self.assertNotIn("CP002", {item.code for item in context.exception.diagnostics})

    def test_stacked_bar_uses_separate_positive_and_negative_accumulators(self) -> None:
        payload = fixture("bar-chart")
        payload.update(
            categories=["Gain", "Loss"], mode="stacked",
            series=[
                {"id": "a", "label": "A", "values": [3, -2]},
                {"id": "b", "label": "B", "values": [4, -5]},
            ],
        )
        payload.pop("focus_series", None)
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        gain = [item for item in result.semantic.marks if item["category"] == "Gain"]
        loss = [item for item in result.semantic.marks if item["category"] == "Loss"]
        gain_boxes = [result.layout.marks[item["id"]] for item in gain]
        loss_boxes = [result.layout.marks[item["id"]] for item in loss]

        self.assertEqual(1, len({item.x for item in gain_boxes}))
        self.assertEqual(1, len({item.x for item in loss_boxes}))
        self.assertGreaterEqual(result.plan.scale.domain_max, 7)
        self.assertLessEqual(result.plan.scale.domain_min, -7)
        labels = {item.text for item in result.scene.primitives if isinstance(item, SceneText)}
        self.assertIn("7 types", labels)
        self.assertIn("-7 types", labels)

    def test_stacked_bar_numerical_invariants_hold_across_bounded_values(self) -> None:
        for offset in range(-5, 6):
            payload = fixture("bar-chart")
            values = ([offset, 4], [3, -2], [-1, 5])
            payload.update(
                categories=["A", "B"], mode="stacked",
                series=[{"id": f"s{index}", "label": f"S{index}", "values": list(series_values)} for index, series_values in enumerate(values)],
            )
            payload.pop("focus_series", None)
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            positive = [sum(max(0, series[index]) for series in values) for index in range(2)]
            negative = [sum(min(0, series[index]) for series in values) for index in range(2)]
            with self.subTest(offset=offset):
                self.assertGreaterEqual(result.plan.scale.domain_max, max(positive))
                self.assertLessEqual(result.plan.scale.domain_min, min(negative))
                self.assertEqual(6, len(result.semantic.marks))

    def test_reference_lines_are_bounded_to_data_domain(self) -> None:
        for kind in ("bar-chart", "line-chart"):
            payload = fixture(kind)
            payload["reference_lines"] = [{"id": "target", "label": "Target", "value": 10 if kind == "bar-chart" else 90}]
            with self.subTest(kind=kind):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertIn("reference:target", result.scene.reading_order)
                self.assertIn('id="reference:target"', render_svg(result.scene))

            invalid = deepcopy(payload)
            invalid["reference_lines"][0]["value"] = 1_000_000
            with self.assertRaises(DrawingCompilationError):
                DEFAULT_COMPILER_REGISTRY.compile_payload(invalid)

    def test_bar_line_and_candlestick_annotations_are_semantic_and_stable(self) -> None:
        payloads = []
        bar = fixture("bar-chart")
        bar["annotations"] = [{"id": "peak", "text": "Coverage reaches its peak", "series": "covered", "category": "V5"}]
        payloads.append(bar)
        line = fixture("line-chart")
        line["annotations"] = [{"id": "pass", "text": "Validation reaches full pass", "series": "valid", "category": "V5"}]
        payloads.append(line)
        candle = fixture("candlestick")
        candle["annotations"] = [{"id": "high", "text": "The final high reaches 99", "period": "d7", "field": "high"}]
        payloads.append(candle)

        for payload in payloads:
            with self.subTest(kind=payload["kind"]):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertEqual(1, len(result.scene.annotations))
                self.assertIn(result.scene.annotations[0].id, result.scene.reading_order)
                self.assertIn(f'id="{result.scene.annotations[0].id}"', render_svg(result.scene))

    def test_waterfall_subtotal_verifies_running_total_and_accessible_table(self) -> None:
        payload = fixture("waterfall")
        payload["contributions"].insert(2, {"id": "subtotal", "label": "Subtotal", "value": 74, "kind": "subtotal"})
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        table = accessible_data(result)
        row = next(item for item in table.rows if item[0] == "Subtotal")

        self.assertEqual(("Subtotal", "", "74"), row)
        self.assertEqual(98.0, result.plan.end)

        payload["contributions"][2]["value"] = 75
        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("WF008", {item.code for item in context.exception.diagnostics})

    def test_explicit_value_format_changes_labels_not_semantic_numbers(self) -> None:
        payload = fixture("bar-chart")
        payload.update(
            categories=["A"],
            series=[{"id": "value", "label": "Value", "values": [1234.5]}],
            unit=" USD",
            locale="en-GB",
            value_format={"precision": 2, "compact": False, "grouping": True, "unit_position": "suffix"},
        )
        payload.pop("focus_series", None)
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        labels = {item.text for item in result.scene.primitives if isinstance(item, SceneText)}

        self.assertEqual(1234.5, result.semantic.marks[0]["value"])
        self.assertIn("1,234.50 USD", labels)

        for field, value in (
            ("locale", "fr-FR"),
            ("unit", "x" * 13),
            ("value_format", {"precision": 9}),
        ):
            invalid = deepcopy(payload)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(DrawingCompilationError):
                DEFAULT_COMPILER_REGISTRY.compile_payload(invalid)

    def test_blank_unit_and_source_render_as_absent(self) -> None:
        cases = (
            ("bar-chart", "unit"),
            ("donut-chart", "unit"),
            ("line-chart", "unit"),
            ("waterfall", "unit"),
            ("candlestick", "unit"),
            ("gantt", "source"),
            ("heatmap", "unit"),
            ("heatmap", "source"),
            ("scatter", "source"),
        )
        for kind, field in cases:
            for blank in ("", "   "):
                with self.subTest(kind=kind, field=field, blank=blank):
                    payload = showcase_fixture(kind)
                    payload[field] = blank
                    absent = showcase_fixture(kind)
                    absent.pop(field, None)

                    self.assertEqual(scene_texts(absent), scene_texts(payload))

    def test_blank_axis_unit_renders_as_absent(self) -> None:
        for kind, axis in (("scatter", "y_axis"), ("heatmap", "x_axis")):
            with self.subTest(kind=kind, axis=axis):
                payload = showcase_fixture(kind)
                payload[axis]["unit"] = "   "
                absent = showcase_fixture(kind)
                absent[axis].pop("unit", None)

                self.assertEqual(scene_texts(absent), scene_texts(payload))
