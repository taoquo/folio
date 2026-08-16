import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.output import OUTPUT_VARIANT_NAMES, normalize_output_variant, variant_defs
from renderers.svg import render_svg

FIXTURE = ROOT / "references" / "fixtures" / "flowchart" / "branching.json"


def _scene():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact")


class VariantContractTests(TestCase):
    def test_variant_names_are_stable(self):
        self.assertEqual(("plain", "sketchy", "motion"), OUTPUT_VARIANT_NAMES)

    def test_unknown_variant_raises(self):
        with self.assertRaises(ValueError):
            normalize_output_variant("neon")

    def test_plain_variant_injects_nothing(self):
        self.assertEqual("", variant_defs("plain", "ns", 5))

    def test_default_render_is_plain_and_backwards_compatible(self):
        result = _scene()
        default = render_svg(result.scene, result.profile)
        plain = render_svg(result.scene, result.profile, variant="plain")
        self.assertEqual(default, plain)
        self.assertIn('data-folio-variant="plain"', default)
        self.assertNotIn("feTurbulence", default)
        self.assertNotIn("folio-reveal", default)


class SketchyVariantTests(TestCase):
    def test_sketchy_adds_a_namespaced_displacement_filter(self):
        result = _scene()
        markup = render_svg(result.scene, result.profile, variant="sketchy", namespace="demo")
        self.assertIn('id="demo--sketchy"', markup)
        self.assertIn("feTurbulence", markup)
        self.assertIn("feDisplacementMap", markup)
        self.assertIn("filter:url(#demo--sketchy)", markup)

    def test_sketchy_excludes_the_canvas_rect_from_the_filter(self):
        result = _scene()
        markup = render_svg(result.scene, result.profile, variant="sketchy")
        self.assertIn('data-folio-role="canvas"', markup)
        self.assertIn('rect:not([data-folio-role])', markup)

    def test_sketchy_keeps_geometry_text_and_reading_order_identical(self):
        result = _scene()
        plain = render_svg(result.scene, result.profile, namespace="demo")
        sketchy = render_svg(result.scene, result.profile, namespace="demo", variant="sketchy")
        stripped = sketchy.replace(variant_defs("sketchy", "demo", 0), "", 1)
        self.assertEqual(
            plain.replace('data-folio-variant="plain"', 'data-folio-variant="sketchy"'),
            stripped,
        )

    def test_sketchy_changes_the_rasterised_png(self):
        result = _scene()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for variant in ("plain", "sketchy"):
                (root / f"{variant}.svg").write_text(
                    render_svg(result.scene, result.profile, variant=variant), encoding="utf-8"
                )
                subprocess.run(
                    ["rsvg-convert", "-w", "640", str(root / f"{variant}.svg"), "-o", str(root / f"{variant}.png")],
                    check=True,
                    capture_output=True,
                )
            with Image.open(root / "plain.png") as plain, Image.open(root / "sketchy.png") as sketchy:
                diff = ImageChops.difference(plain.convert("RGB"), sketchy.convert("RGB"))
                self.assertIsNotNone(diff.getbbox())


class MotionVariantTests(TestCase):
    def test_motion_uses_reduced_motion_guarded_css_keyframes(self):
        result = _scene()
        markup = render_svg(result.scene, result.profile, variant="motion")
        self.assertIn("@media (prefers-reduced-motion: no-preference)", markup)
        self.assertIn("@keyframes folio-reveal", markup)
        self.assertIn("[data-reading-order]", markup)

    def test_motion_stagger_is_bounded_and_deterministic(self):
        first = variant_defs("motion", "demo", 40)
        second = variant_defs("motion", "demo", 40)
        self.assertEqual(first, second)
        self.assertIn("animation-delay:0ms", first)
        self.assertIn("animation-delay:700ms", first)
        self.assertNotIn("animation-delay:770ms", first)

    def test_motion_degrades_to_plain_in_static_png_export(self):
        result = _scene()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for variant in ("plain", "motion"):
                (root / f"{variant}.svg").write_text(
                    render_svg(result.scene, result.profile, variant=variant), encoding="utf-8"
                )
                subprocess.run(
                    ["rsvg-convert", "-w", "640", str(root / f"{variant}.svg"), "-o", str(root / f"{variant}.png")],
                    check=True,
                    capture_output=True,
                )
            with Image.open(root / "plain.png") as plain, Image.open(root / "motion.png") as motion:
                diff = ImageChops.difference(plain.convert("RGB"), motion.convert("RGB"))
                self.assertIsNone(diff.getbbox())

    def test_motion_keeps_accessibility_markup_intact(self):
        result = _scene()
        markup = render_svg(result.scene, result.profile, variant="motion", namespace="demo")
        self.assertIn('aria-labelledby="demo--drawing-title demo--drawing-description"', markup)
        self.assertIn('data-folio-id="drawing-description"', markup)


class VariantMatrixTests(TestCase):
    def test_every_catalog_type_renders_in_every_variant(self):
        catalog = json.loads((ROOT / "references" / "fixtures" / "diagram-catalog.json").read_text())
        for item in catalog["diagrams"]:
            payload = json.loads((ROOT / item["source"]).read_text(encoding="utf-8"))
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact")
            for variant in OUTPUT_VARIANT_NAMES:
                with self.subTest(kind=item["kind"], variant=variant):
                    markup = render_svg(result.scene, result.profile, variant=variant)
                    self.assertTrue(markup.startswith("<svg "))
                    self.assertTrue(markup.endswith("</svg>"))
                    self.assertIn(f'data-folio-variant="{variant}"', markup)
