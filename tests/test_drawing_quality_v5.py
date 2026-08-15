import json
import sys
from pathlib import Path
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneGroup,
    SceneLine,
    SceneRect,
    SceneStyle,
    SceneText,
)
from drawing.theme.folio import DEFAULT_FOLIO_THEME
from drawing.validation import DrawingDiagnostic, contrast_ratio, validate_scene_quality


PARCHMENT = "#F6F0EA"
INK = "#191514"
BRAND = "#B83D2E"


def _scene(*primitives, width=320, height=240, title_size=20) -> ResolvedScene:
    return ResolvedScene(
        width,
        height,
        PARCHMENT,
        SceneText("Quality", width // 2, 32, INK, title_size, "Charter", "middle"),
        (),
        (),
        (),
        primitives=tuple(primitives),
    )


def _codes(scene: ResolvedScene) -> set[str]:
    return {item.code for item in validate_scene_quality(scene)}


class DrawingQualityV5Tests(TestCase):
    def test_empty_scene_is_an_error(self) -> None:
        self.assertIn("VQ100", _codes(_scene()))

    def test_canvas_use_detects_low_utilization_and_asymmetry(self) -> None:
        mark = SceneRect("mark", SceneBox(8, 64, 24, 24), SceneStyle(INK, "none"))
        codes = _codes(_scene(mark))
        self.assertIn("VQ101", codes)
        self.assertIn("VQ102", codes)

    def test_accent_budget_counts_elements_and_area(self) -> None:
        marks = tuple(
            SceneRect(f"focus-{index}", SceneBox(32 + index * 88, 72, 72, 72), SceneStyle(BRAND, "none"))
            for index in range(3)
        )
        codes = _codes(_scene(*marks))
        self.assertIn("VQ103", codes)
        self.assertIn("VQ104", codes)

    def test_empty_compartment_is_an_error_inside_nested_group(self) -> None:
        group = SceneGroup(
            "outer",
            (SceneGroup(
                "class",
                (
                    SceneRect("class-box", SceneBox(40, 64, 240, 144), SceneStyle("#FBF7F3", INK, 1)),
                    SceneText("Customer", 160, 92, INK, 14, "Charter", "middle"),
                    SceneLine("attributes-divider", (40, 112), (280, 112), SceneStyle("none", INK, 1)),
                ),
            ),),
        )
        self.assertIn("VQ105", _codes(_scene(group)))

    def test_small_text_requires_45_to_1_contrast(self) -> None:
        text = SceneText("metadata", 64, 100, "#958A84", 12, "Charter")
        self.assertIn("VQ106", _codes(_scene(text)))

    def test_large_text_accepts_3_to_1_contrast(self) -> None:
        text = SceneText("Large", 64, 100, "#7F736C", 18, "Charter")
        self.assertNotIn("VQ106", _codes(_scene(text)))

    def test_low_contrast_non_text_graphic_warns(self) -> None:
        circle = SceneCircle("control", 160, 120, 36, SceneStyle("none", "#B7ADA6", 2))
        diagnostics = validate_scene_quality(_scene(circle))
        self.assertTrue(any(item.code == "VQ107" and item.object_id == "control" for item in diagnostics))

    def test_decorative_hairline_does_not_trigger_graphic_contrast(self) -> None:
        line = SceneLine("divider", (40, 120), (280, 120), SceneStyle("none", "#E9DED4", 1))
        self.assertNotIn("VQ107", _codes(_scene(line)))

    def test_contrast_ratio_known_values(self) -> None:
        self.assertAlmostEqual(21.0, contrast_ratio("#000000", "#FFFFFF"), places=6)
        self.assertAlmostEqual(1.0, contrast_ratio("#ABCDEF", "#ABCDEF"), places=6)
        self.assertIsNone(contrast_ratio("none", "#FFFFFF"))

    def test_default_stone_is_accessible_on_supported_light_surfaces(self) -> None:
        for surface in (
            DEFAULT_FOLIO_THEME.parchment,
            DEFAULT_FOLIO_THEME.ivory,
            DEFAULT_FOLIO_THEME.brand_tint,
        ):
            with self.subTest(surface=surface):
                self.assertGreaterEqual(contrast_ratio(DEFAULT_FOLIO_THEME.stone, surface), 4.5)

    def test_all_registered_kinds_pass_through_the_quality_gate(self) -> None:
        sentinel = DrawingDiagnostic("TASTE", "VQ999", "quality gate sentinel")
        fixture_dir = ROOT / "references" / "fixtures" / "minimal"
        with mock.patch("drawing.compiler.validate_scene_quality", return_value=[sentinel]):
            for kind in DEFAULT_COMPILER_REGISTRY.kinds:
                with self.subTest(kind=kind):
                    payload = json.loads((fixture_dir / f"{kind}.json").read_text())
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertIn("VQ999", {item.code for item in result.diagnostics})
                    self.assertEqual(
                        sum(item.level in {"WARNING", "TASTE"} for item in result.diagnostics),
                        result.metrics.taste_warnings,
                    )

    def test_canonical_minimal_fixtures_have_no_quality_errors(self) -> None:
        fixture_dir = ROOT / "references" / "fixtures" / "minimal"
        for path in sorted(fixture_dir.glob("*.json")):
            with self.subTest(kind=path.stem):
                payload = json.loads(path.read_text())
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                errors = [
                    item for item in result.diagnostics
                    if item.level == "ERROR" and item.code.startswith("VQ")
                ]
                self.assertEqual([], errors)
