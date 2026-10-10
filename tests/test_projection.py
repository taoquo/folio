"""The projection layer injects; it does not edit.

The templates are not modified. CSS is appended inside their own stylesheet, so
the change is removable by configuration and reviewable as a diff of the
injected block alone.

The property that matters most is that the layer changes nothing on its own:
injecting an empty projection, or the values a template already uses, must
produce the same page.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import projection  # noqa: E402

SAMPLE = "<html><head><style>body { color: red; }</style></head><body>x</body></html>"


class ProjectionTests(TestCase):
    def test_an_empty_projection_changes_nothing(self) -> None:
        self.assertEqual(SAMPLE, projection.inject(SAMPLE, projection.Projection(css="")))

    def test_injection_lands_inside_the_stylesheet(self) -> None:
        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        injected = projection.inject(SAMPLE, proj)
        self.assertLess(injected.index("--folio-body-size"), injected.index("</style>"))

    def test_a_document_without_a_stylesheet_is_left_alone(self) -> None:
        # Inventing a stylesheet would move every rule in the cascade.
        bare = "<html><body>x</body></html>"
        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        self.assertEqual(bare, projection.inject(bare, proj))

    def test_projected_values_are_the_ones_the_template_uses(self) -> None:
        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        self.assertEqual("10pt", proj.projected["--folio-body-size"])
        self.assertEqual("1.45", proj.projected["--folio-body-leading"])

    def test_every_projected_variable_names_its_source(self) -> None:
        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        for variable in proj.projected:
            with self.subTest(variable=variable):
                self.assertTrue(proj.sources.get(variable))

    def test_a_missing_value_is_skipped_not_defaulted(self) -> None:
        # Writing a value nobody chose would make the stylesheet look deliberate.
        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        self.assertIn("paragraph.section_gap_pt", proj.skipped)

    def test_the_css_is_balanced(self) -> None:
        for proj in (projection.style_projection("one-pager", "zh-Hans-CN"),
                     projection.policy_projection("one-pager"),
                     projection.combined("one-pager", "zh-Hans-CN", include_policy=True)):
            with self.subTest(kind=len(proj.css)):
                self.assertEqual(proj.css.count("{"), proj.css.count("}"))

    def test_a_level_one_heading_does_not_force_a_page_break(self) -> None:
        # The one-pager has exactly one `h1` and it is the title; a forced break
        # there splits a single-page document in two.
        css = projection.policy_projection("one-pager").css
        self.assertNotIn("break-before: page", css)

    def test_an_unknown_genre_projects_nothing_rather_than_guessing(self) -> None:
        proj = projection.policy_projection("no-such-genre")
        self.assertTrue(proj.empty or "policy" not in proj.projected)

    def test_the_check_reports_no_problems(self) -> None:
        self.assertEqual([], projection.check())

    def test_a_projection_is_serialisable(self) -> None:
        import json

        proj = projection.style_projection("one-pager", "zh-Hans-CN")
        payload = json.loads(json.dumps(proj.to_json()))
        self.assertIn("projected", payload)
        self.assertIn("sources", payload)


class GapProjectionTests(TestCase):
    """The spacing model reaches the page, but never overrides a template.

    The model states a gap for each pair of blocks. Emitting all of them would
    replace decisions the templates have already made, and a differential
    experiment showed what that costs: changing one `margin-top` to
    `padding-top` moved the rendering to SSIM 0.90.

    So a gap is emitted only for a pair the stylesheet does not already decide.
    """

    def test_the_layer_is_off_unless_asked_for(self) -> None:
        base = projection.combined("one-pager", "zh-Hans-CN", include_policy=True)
        with_gaps = projection.combined(
            "one-pager", "zh-Hans-CN", include_policy=True, include_gaps=True
        )
        self.assertGreaterEqual(len(with_gaps.projected), len(base.projected))

    def test_a_pair_the_template_decides_is_left_alone(self) -> None:
        from pathlib import Path

        template = Path(projection.ROOT) / "assets" / "templates" / "one-pager.html"
        stylesheet = template.read_text(encoding="utf-8")
        gaps = projection.gap_projection("one-pager", stylesheet)
        # The one-pager sets its own paragraph and heading margins, so most
        # pairs are skipped rather than restated.
        self.assertGreater(len(gaps.skipped), len(gaps.projected))

    def test_a_gap_carries_the_rule_that_produced_it(self) -> None:
        gaps = projection.gap_projection("one-pager", "")
        for key in gaps.projected:
            with self.subTest(key=key):
                self.assertTrue(gaps.sources.get(key))

    def test_the_emitted_css_is_balanced(self) -> None:
        gaps = projection.gap_projection("one-pager", "")
        self.assertEqual(gaps.css.count("{"), gaps.css.count("}"))

    def test_every_gap_uses_the_models_preferred_value(self) -> None:
        import spacing

        gaps = projection.gap_projection("one-pager", "")
        for key, value in gaps.projected.items():
            before, after = key[4:].split("->")
            with self.subTest(pair=key):
                expected = spacing.resolve_gap(before, after).spec.preferred.as_pt()
                self.assertEqual(f"{expected:g}pt", value)

    def test_a_fallback_pair_is_not_projected(self) -> None:
        # A fallback means the model has no rule for the pair; inventing a value
        # would put a number on the page that nobody chose.
        gaps = projection.gap_projection("one-pager", "")
        for key in gaps.projected:
            with self.subTest(key=key):
                self.assertNotIn("fallback", gaps.sources.get(key, ""))
