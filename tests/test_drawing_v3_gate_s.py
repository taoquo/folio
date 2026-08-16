import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_models import load_diagram_spec_file
from drawing.models import DrawingPlan, LegendItemPlan, LegendPlan
from drawing.layout.models import LayoutBox, LayoutEdge, LayoutResult
from drawing.pipeline import compile_drawing_plan, drawing_plan_from_spec
from drawing.review import write_review_bundle
from drawing.review import _visual_diff
from drawing.schema import validate_plan_payload
from drawing.validation import DrawingCompilationError, validate_scene_accessibility, validate_scene_primitives
from drawing.validation.layout import validate_layout
from drawing.output import apply_html_output_profile
from drawing.scene import ResolvedScene, SceneBox, SceneCircle, SceneClip, SceneGroup, ScenePath, SceneRect, SceneStyle, SceneText
from renderers.svg import render_svg


class DrawingV3GateSTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-demo.json")

    def test_aud_010_unknown_pictogram_is_schema_error_not_keyerror(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        payload["nodes"][0]["pictogram"] = "unknown"

        issues = validate_plan_payload(payload)

        self.assertTrue(any("pictogram is invalid" in item for item in issues))
        with self.assertRaises(ValueError) as context:
            DrawingPlan.from_dict(payload)
        self.assertNotIsInstance(context.exception, KeyError)

    def test_architecture_compile_rejects_invalid_spine_before_layout(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        payload["composition"]["spine"].append("missing")

        with self.assertRaises(ValueError):
            DrawingPlan.from_dict(payload)

    def test_aud_001_registry_rejects_unversioned_authored_plan(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        payload.pop("schema_version")

        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

        self.assertEqual("schema", context.exception.stage)
        self.assertTrue(any(item.code == "CP003" for item in context.exception.diagnostics))

    def test_aud4_005_architecture_semantic_input_rejects_unknown_fields(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        payload = json.loads((ROOT / "references" / "fixtures" / "architecture-demo.json").read_text())
        payload["pixel_override"] = 12
        with self.assertRaises(DrawingCompilationError) as top_level:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("unknown field", str(top_level.exception))

        payload.pop("pixel_override")
        payload["nodes"][0]["x"] = 48
        with self.assertRaises(DrawingCompilationError) as nested:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("architecture node has unknown field", str(nested.exception))

    def test_aud4_007_unversioned_architecture_semantic_input_migrates_to_v3(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        payload = json.loads((ROOT / "references" / "fixtures" / "minimal" / "architecture.json").read_text())
        payload.pop("schema_version")
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

        self.assertEqual("3.0", result.normalized_input["schema_version"])
        self.assertEqual("3.0", result.metadata.input_schema_version)
        self.assertEqual("architecture@3", result.metadata.registry_key)

    def test_aud_011_legend_that_cannot_fit_fails_closed(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        items = tuple(
            LegendItemPlan("primary-flow", f"Very long legend label {index} xxxxxxxxxxxxxxxxxxxx")
            for index in range(6)
        )
        drawing = replace(drawing, legend=LegendPlan("Legend", items))

        with self.assertRaises(DrawingCompilationError) as context:
            compile_drawing_plan(drawing)

        self.assertEqual("scene", context.exception.stage)

    def test_aud_013_visual_diff_does_not_resize_dimension_changes_away(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp) / "base.png"
            current = Path(temp) / "current.png"
            diff = Path(temp) / "diff.png"
            Image.new("RGB", (10, 10), "#B83D2E").save(base)
            Image.new("RGB", (20, 20), "#B83D2E").save(current)

            result = _visual_diff(base, current, diff)

            self.assertFalse(result["dimensions_match"])
            self.assertEqual([10, 10], result["baseline_size"])
            self.assertEqual([20, 20], result["current_size"])

    def test_output_profiles_have_explicit_svg_contracts(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        _layout, scene = compile_drawing_plan(drawing)

        artifact = render_svg(scene, "artifact")
        embed = render_svg(scene, "embed")

        self.assertIn('width="960" height="540"', artifact)
        self.assertIn('width="100%"', embed)

    def test_aud_004_page_preview_removes_static_minimum_width(self) -> None:
        source = (ROOT / "assets" / "diagrams" / "state-machine.html").read_text()
        resolved = apply_html_output_profile(source, "page-preview")

        self.assertIn("min-width: 0 !important", resolved)
        self.assertIn("@page { size: A4", resolved)

    def test_aud_012_canvas_validator_requires_complete_reading_order(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        _layout, scene = compile_drawing_plan(drawing)
        invalid = replace(scene, reading_order=scene.reading_order[:-1])

        self.assertTrue(any(item.code == "AX201" for item in validate_scene_accessibility(invalid)))

    def test_type_neutral_primitives_render_without_semantic_branches(self) -> None:
        title = SceneText("Primitive", 160, 32, "#191514", 20, "Charter", "middle")
        scene = ResolvedScene(
            320, 240, "#F6F0EA", title, (), (), (),
            primitives=(
                SceneGroup(
                    "marks",
                    (
                        SceneRect("bar", SceneBox(40, 80, 64, 120), SceneStyle("#B83D2E", "none")),
                        SceneCircle("point", 200, 120, 16, SceneStyle("#FBF7F3", "#191514", 1)),
                    ),
                ),
            ),
        )

        svg = render_svg(scene)

        self.assertIn('data-folio-id="bar"', svg)
        self.assertIn('data-folio-id="point"', svg)
        self.assertFalse(validate_scene_primitives(scene))

    def test_aud_016_type_neutral_primitives_reject_duplicate_ids_and_unknown_clips(self) -> None:
        title = SceneText("Primitive", 160, 32, "#191514", 20, "Charter", "middle")
        scene = ResolvedScene(
            320, 240, "#F6F0EA", title, (), (), (),
            primitives=(
                SceneClip("clip", SceneBox(20, 60, 80, 80)),
                SceneRect("clip", SceneBox(40, 80, 40, 40), SceneStyle("#B83D2E", "none")),
                SceneGroup("marks", (), clip_id="missing"),
            ),
        )

        diagnostics = validate_scene_primitives(scene)

        self.assertTrue(any(item.code == "PV001" for item in diagnostics))
        self.assertTrue(any(item.code == "PV002" for item in diagnostics))
        self.assertTrue(any(item.code == "AX203" for item in validate_scene_accessibility(scene)))

    def test_v3_path_geometry_outside_canvas_fails_closed(self) -> None:
        title = SceneText("Path", 160, 32, "#191514", 20, "Charter", "middle")
        scene = ResolvedScene(
            320, 240, "#F6F0EA", title, (), (), (),
            primitives=(ScenePath("outside", "M 40 40 L 400 40", SceneStyle("none", "#191514", 1)),),
        )

        self.assertTrue(any(item.code == "PV107" for item in validate_scene_primitives(scene)))

    def test_aud_009_architecture_overflow_cannot_reach_scene_export(self) -> None:
        drawing = replace(drawing_plan_from_spec(self.spec), width=320)

        with self.assertRaises(DrawingCompilationError) as context:
            compile_drawing_plan(drawing)

        self.assertEqual("layout", context.exception.stage)

    def test_aud_015_layout_endpoint_must_touch_target_boundary(self) -> None:
        boxes = {
            "source": LayoutBox(0, 0, 40, 40),
            "target": LayoutBox(100, 0, 40, 40),
        }
        edge = LayoutEdge("source", "target", [(40, 20), (120, 20)])
        layout = LayoutResult(boxes, [edge], LayoutBox(0, 0, 140, 40))

        issues = validate_layout(layout, 200, 100)

        self.assertTrue(any("does not terminate on target" in item for item in issues))

    def test_aud_020_review_manifest_contains_release_evidence(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        result = DEFAULT_COMPILER_REGISTRY.compile_architecture_spec(self.spec)

        def fake_png(_svg: Path, output: Path, width: int = 1920, **_kwargs) -> None:
            Image.new("RGB", (width, 1080), "#F6F0EA").save(output)

        def fake_pdf(_svg: Path, output: Path, _title: str, _language: str, _profile: str) -> None:
            output.write_bytes(b"%PDF-1.4\n")

        with TemporaryDirectory() as temp, mock.patch("drawing.review.export_png", side_effect=fake_png), mock.patch("drawing.review.export_pdf", side_effect=fake_pdf):
            manifest = write_review_bundle(
                result.semantic, result.plan, result.layout, result.scene, temp,
                diagnostics=result.diagnostics, metrics=result.metrics, profile=result.profile,
                normalized_input=result.normalized_input, compilation_metadata=result.metadata,
            )

        self.assertEqual("3.0", manifest["compiler_contract"])
        self.assertEqual("architecture@3", manifest["compilation"]["registry_key"])
        self.assertEqual("not-applicable", manifest["approval_state"])
        self.assertIn("input.json", manifest["digests"])

    def test_aud_021_review_manifest_records_theme_and_variant(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        result = DEFAULT_COMPILER_REGISTRY.compile_architecture_spec(self.spec, theme="dark")

        def fake_png(_svg: Path, output: Path, width: int = 1920, **_kwargs) -> None:
            Image.new("RGB", (width, 1080), "#F6F0EA").save(output)

        def fake_pdf(_svg: Path, output: Path, _title: str, _language: str, _profile: str) -> None:
            output.write_bytes(b"%PDF-1.4\n")

        with TemporaryDirectory() as temp, mock.patch("drawing.review.export_png", side_effect=fake_png), mock.patch("drawing.review.export_pdf", side_effect=fake_pdf):
            manifest = write_review_bundle(
                result.semantic, result.plan, result.layout, result.scene, temp,
                diagnostics=result.diagnostics, metrics=result.metrics, profile=result.profile,
                theme=result.theme, variant="sketchy",
                normalized_input=result.normalized_input, compilation_metadata=result.metadata,
            )
            svg = (Path(temp) / "drawing.svg").read_text(encoding="utf-8")

        self.assertEqual("dark", manifest["theme"])
        self.assertEqual("sketchy", manifest["variant"])
        self.assertIn('data-folio-variant="sketchy"', svg)
