import sys
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stabilize


class StabilizeNormalizationTests(TestCase):
    def test_rgba_is_flattened_onto_parchment(self) -> None:
        css, changed = stabilize.normalize_rgba("a { background: rgba(0, 0, 0, 0.5); }")

        self.assertEqual(1, changed)
        self.assertNotIn("rgba(", css)
        self.assertIn("#7A7A76", css)

    def test_rgba_flattening_is_a_no_op_for_solid_hex(self) -> None:
        css, changed = stabilize.normalize_rgba("a { background: #F5F4ED; }")

        self.assertEqual(0, changed)
        self.assertEqual("a { background: #F5F4ED; }", css)

    def test_cool_grays_are_remapped_to_warm_neutrals(self) -> None:
        blocked = sorted(stabilize.COOL_GRAY_BLOCKLIST)[0]
        css, changed = stabilize.normalize_cool_grays(f"a {{ color: {blocked}; }}")

        self.assertEqual(1, changed)
        self.assertIn(css[css.index("#") : css.index("#") + 7], {"#4B3E39", "#87867F", "#E9DED4"})

    def test_line_heights_are_clamped_into_range(self) -> None:
        css, changed = stabilize.clamp_line_heights("a { line-height: 3.4; }\nb { line-height: 1.5; }", 1.2, 1.8)

        self.assertEqual(1, changed)
        self.assertIn("line-height: 1.8;", css)
        self.assertIn("line-height: 1.5;", css)

    def test_css_round_trip_preserves_surrounding_html(self) -> None:
        html = "<html><style>\na { color: red; }\n</style><body>x</body></html>"
        css, match = stabilize.extract_css(html)

        self.assertEqual("a { color: red; }", css.strip())
        self.assertEqual(html, stabilize.replace_css(html, css, match))

    def test_missing_style_block_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing <style> block"):
            stabilize.extract_css("<html><body>x</body></html>")


class StabilizeTargetResolutionTests(TestCase):
    def test_all_expands_to_every_html_target(self) -> None:
        self.assertEqual(list(stabilize.HTML_TARGETS), stabilize.resolve_targets(["all"]))
        self.assertEqual(list(stabilize.HTML_TARGETS), stabilize.resolve_targets([]))

    def test_source_file_names_work_as_aliases(self) -> None:
        self.assertEqual(["one-pager", "resume-en"], stabilize.resolve_targets(["one-pager.html", "resume-en"]))

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown target: slides"):
            stabilize.resolve_targets(["slides"])

    def test_every_target_points_at_an_existing_template(self) -> None:
        for target, (source, max_pages) in stabilize.HTML_TARGETS.items():
            self.assertTrue((stabilize.TEMPLATES / source).is_file(), target)
            self.assertGreater(max_pages, 0, target)


class StabilizeProfileValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profiles = stabilize.load_json(stabilize.PROFILES_FILE)

    def test_shipped_profiles_pass_validation_for_every_target(self) -> None:
        defaults = self.profiles.get("defaults", {})
        for target in stabilize.HTML_TARGETS:
            profile = stabilize.deep_merge(defaults, self.profiles.get("targets", {}).get(target, {}))
            stabilize.validate_profile(profile, target)

    def test_inverted_range_is_rejected(self) -> None:
        defaults = self.profiles.get("defaults", {})
        broken = stabilize.deep_merge(defaults, {"line_height": {"min": 2.0, "max": 1.0}})

        with self.assertRaisesRegex(ValueError, "line_height.min"):
            stabilize.validate_profile(broken, "one-pager")

    def test_non_numeric_range_bound_is_rejected(self) -> None:
        defaults = self.profiles.get("defaults", {})
        broken = stabilize.deep_merge(defaults, {"body_font_size_pt": {"min": "small", "max": 12}})

        with self.assertRaisesRegex(ValueError, "must be numeric"):
            stabilize.validate_profile(broken, "one-pager")
