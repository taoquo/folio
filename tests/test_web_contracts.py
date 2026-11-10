"""Contracts for the Web reading-page scenario.

These tests hold the contract module to itself: ids unique, vocabularies closed,
ranges ordered, the caption grammar accepting what the docs show and rejecting
what they forbid. They do not render a page; `check_web.py` does that.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402


class ContractTests(unittest.TestCase):
    def test_acceptance_keys_are_unique_and_cover_16(self) -> None:
        keys = [item.key for item in C.ACCEPTANCE]
        self.assertEqual(len(keys), 16)
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_acceptance_kind_is_known(self) -> None:
        for item in C.ACCEPTANCE:
            self.assertIn(item.kind, {"machine", "semi", "manual"})

    def test_status_vocabulary_is_closed_and_split(self) -> None:
        self.assertEqual(set(C.STATUS_VOCAB),
                         set(C.STATUS_GROUPS["package"]) | set(C.STATUS_GROUPS["integration"]))
        self.assertFalse(set(C.STATUS_GROUPS["package"]) & set(C.STATUS_GROUPS["integration"]))

    def test_concept_to_series_uses_the_six_series(self) -> None:
        self.assertEqual(set(C.CONCEPT_TO_SERIES), {
            "delivered", "info", "component", "passed", "attention",
            "pending", "enhance", "change", "input", "risk"})
        self.assertTrue(all(1 <= value <= 6 for value in C.CONCEPT_TO_SERIES.values()))

    def test_density_ranges_are_ordered(self) -> None:
        for name, (low, high) in C.DENSITY.items():
            with self.subTest(item=name):
                self.assertLess(low, high)
        self.assertLess(C.MEASURE_CHARS[0], C.MEASURE_CHARS[1])

    def test_caption_grammar_accepts_a_contract_caption(self) -> None:
        value = "图 W-1 · 编码器与解码器堆栈"
        self.assertTrue(C.FIGCAPTION.match(value))

    def test_caption_grammar_rejects_a_missing_number(self) -> None:
        value = "编码器与解码器堆栈"
        self.assertIsNone(C.FIGCAPTION.match(value))

    def test_caption_grammar_rejects_a_provenance_tail(self) -> None:
        # The composition and the axis belong on the figure's data attributes,
        # not in the sentence a reader sees.
        for tail in (" composition: layered", " axis: left-right"):
            with self.subTest(tail=tail):
                value = f"图 W-1 · 编码器与解码器堆栈 ·{tail}"
                self.assertIsNone(C.FIGCAPTION.match(value))

    def test_caption_grammar_accepts_an_english_caption(self) -> None:
        value = "Figure W-1 · Encoder and decoder stacks"
        self.assertTrue(C.FIGCAPTION.match(value))

    def test_semantic_roles_are_the_ten_meanings(self) -> None:
        self.assertEqual(set(C.SEMANTIC_ROLES), {
            "delivered", "info", "component", "passed", "attention",
            "enhance", "risk", "change", "input", "pending"})
        self.assertEqual(len(C.SEMANTIC_ROLES), len(set(C.SEMANTIC_ROLES)))

    def test_status_vocabulary_is_bilingual_and_still_closed(self) -> None:
        self.assertIn("已实现", C.STATUS_VOCAB)
        self.assertIn("Implemented", C.STATUS_VOCAB)
        self.assertNotIn("Shipped", C.STATUS_VOCAB)
        self.assertEqual(set(C.STATUS_VOCAB),
                         set(C.STATUS_GROUPS["package"]) | set(C.STATUS_GROUPS["integration"]))

    def test_title_bans_cover_the_documented_symbols(self) -> None:
        for token in ("→", "←", "↔", "——", "·"):
            with self.subTest(token=token):
                self.assertIn(token, C.TITLE_BANNED)

    def test_component_patterns_name_a_real_component(self) -> None:
        for _name, _pattern, component in C.COMPONENT_PATTERNS:
            self.assertIn(component, C.PAGE_TYPES["module-archive"]["optional"])

    def test_pages_declare_the_regions_the_checker_requires(self) -> None:
        for name, page in C.PAGE_TYPES.items():
            with self.subTest(page=name):
                self.assertTrue(page["required"])
                self.assertIn(page["body_class"], name)


class WebProjectionTests(unittest.TestCase):
    """The Web page is styled by the engine, not by its own stylesheet."""

    def setUp(self) -> None:
        import projection
        import style_resolver

        self.projection = projection
        self.resolver = style_resolver

    def test_both_languages_resolve_a_web_profile(self) -> None:
        for language in ("zh-Hans-CN", "en"):
            with self.subTest(language=language):
                style = self.resolver.resolve(genre="web-reading", language=language)
                self.assertTrue(style.domains.get("web"), style.violations)

    def test_the_projection_carries_fonts_type_and_spacing(self) -> None:
        for language in ("zh-Hans-CN", "en"):
            with self.subTest(language=language):
                web = self.projection.web_projection("web-reading", language)
                for name in ("--serif", "--mono", "--web-body-size",
                             "--web-space-6", "--web-measure-body"):
                    self.assertIn(name, web.projected)
                self.assertIn("web:", web.sources["--web-body-size"])

    def test_the_template_declares_no_type_or_spacing_literal(self) -> None:
        self.assertEqual([], self.projection.web_template_literals())

    def test_every_semantic_role_has_its_own_colour_in_every_scheme(self) -> None:
        import check_theme_schemes

        for name in check_theme_schemes.profiles():
            with self.subTest(theme=name):
                style = self.resolver.resolve(names={"theme": name})
                marks = {
                    str(style.get(f"color.semantic.{role}")).lower()
                    for role in C.SEMANTIC_ROLES
                }
                self.assertEqual(len(C.SEMANTIC_ROLES), len(marks))


class FigureCaptionTests(unittest.TestCase):
    """The caption describes the drawing the compiler produced, not the label.

    A fixture's `layout` names geometry, and the planner turns that geometry
    into a composition and a reading axis. The page repeats the planner's
    answer, so a caption cannot claim a direction the figure does not read in.
    """

    FIXTURES = ROOT / "references" / "fixtures" / "web" / "reading-demo" / "figures"

    def test_caption_axis_follows_the_planned_reading_direction(self) -> None:
        import web_figures

        expected = {
            "release-gate": ("layered", "top-down"),
            "build-lifecycle": ("pipeline", "left-right"),
            "sign-off": ("pipeline", "left-right"),
        }
        for figure_id, (composition, axis) in expected.items():
            with self.subTest(figure=figure_id):
                figure = web_figures.render_figure(
                    self.FIXTURES / f"{figure_id}.json", figure_id, page_theme=None)
                self.assertEqual(composition, figure.composition)
                self.assertEqual(axis, figure.axis)
                self.assertIn(figure.composition, C.COMPOSITIONS)

    def test_a_series_override_names_the_meaning_not_the_direction(self) -> None:
        import web_figures

        figure = web_figures.render_figure(
            self.FIXTURES / "release-gate.json", "release-gate",
            page_theme=None, composition="hub")

        self.assertEqual("hub", figure.composition)
        self.assertEqual("top-down", figure.axis)


class FigureLegibilityTests(unittest.TestCase):
    """The manifest says what the column delivers, instead of guessing.

    A figure is drawn on a 960-unit stage and scaled into the 660px column, so
    its 7 / 9 / 12 tiers arrive at 4.8 / 6.2 / 8.3px. Enlarging the plate was
    tried and rejected: it enlarged the drawing's empty margin with it. What
    survives is the measurement — every tier the scene draws is recorded, so
    `web_probe.py` and W-FIG-10 can report the delivered size, and P1b has a
    baseline to move.
    """

    FIXTURES = ROOT / "references" / "fixtures" / "web" / "reading-demo" / "figures"

    def _figure(self):
        import web_figures

        return web_figures.render_figure(
            self.FIXTURES / "release-gate.json", "release-gate", page_theme=None)

    def test_manifest_reports_every_tier_the_scene_draws(self) -> None:
        figure = self._figure()
        manifest = figure.manifest_entry()

        self.assertEqual([round(size, 2) for size in figure.text_sizes],
                         manifest["text_sizes"])
        self.assertGreaterEqual(len(figure.text_sizes), 2)
        self.assertEqual(sorted(figure.text_sizes), list(figure.text_sizes))

    def test_min_font_is_the_size_delivered_in_the_slot(self) -> None:
        figure = self._figure()
        framed = figure.view_box[2]

        self.assertAlmostEqual(C.FIGURE["slot"] * min(figure.text_sizes) / framed,
                               figure.min_font_px, places=2)
        self.assertLess(figure.min_font_px, min(figure.text_sizes))

    def test_svg_scales_to_its_slot(self) -> None:
        # The page owns the width; the drawing owns the composition. An
        # intrinsic width here would put a 960-unit plate in a 660px column.
        figure = self._figure()
        root_tag = figure.svg[:figure.svg.index(">") + 1]

        self.assertIn('width="100%"', root_tag)
        self.assertIn('viewBox="', root_tag)

    def test_the_drawing_is_framed_to_its_ink(self) -> None:
        # The plate is the ink plus the framing margin, not the whole stage.
        figure = self._figure()

        self.assertLess(figure.view_box[2], figure.stage[0])
        self.assertGreaterEqual(figure.coverage, C.FIGURE_FIT["coverage_min"])
        self.assertLessEqual(figure.margin_ratio, C.FIGURE_FIT["margin_ratio_max"])

    def test_framing_delivers_larger_type_than_the_full_stage(self) -> None:
        figure = self._figure()
        slot = C.FIGURE["slot"]
        framed = min(figure.text_sizes) * slot / figure.view_box[2]
        full = min(figure.text_sizes) * slot / figure.stage[0]

        self.assertGreater(framed, full)
        self.assertAlmostEqual(framed, figure.min_font_px, places=2)


if __name__ == "__main__":
    unittest.main()
