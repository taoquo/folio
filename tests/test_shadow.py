"""The shadow pipeline reports whether the IR path matches the shipping one.

It exists to answer that question before anything about the deliverable
changes. A difference is information, not failure: the run's exit code reports
whether the comparison worked, and the report says which dimension moved.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import shadow


def _comparison(**overrides) -> shadow.Comparison:
    base = {
        "fixture_id": "f",
        "genre": "one-pager",
        "language": "zh-Hans-CN",
        "legacy_pages": 1,
        "ir_pages": 1,
        "legacy_text": "hello world",
        "ir_text": "hello world",
        "legacy_fonts": ["LXGW-WenKai"],
        "ir_fonts": ["LXGW-WenKai"],
    }
    base.update(overrides)
    return shadow.Comparison(**base)


class ComparisonVerdictTests(TestCase):
    def test_identical_pages_and_fonts_match(self) -> None:
        item = _comparison()
        self.assertTrue(item.pages_match)
        self.assertTrue(item.fonts_match)

    def test_a_page_difference_is_reported(self) -> None:
        item = _comparison(ir_pages=2)
        self.assertFalse(item.pages_match)
        self.assertFalse(item.ok)

    def test_a_lost_font_is_reported(self) -> None:
        item = _comparison(ir_fonts=["Charter"])
        self.assertFalse(item.fonts_match)
        self.assertFalse(item.ok)
        self.assertTrue(item.fonts_missing_from_ir)

    def test_an_extra_font_is_not_a_failure(self) -> None:
        # The IR may need a face the template did not: it carries structure the
        # template held outside its placeholders.
        item = _comparison(ir_fonts=_comparison().legacy_fonts + ["ExtraFace"])
        self.assertTrue(item.fonts_match)
        self.assertEqual(["ExtraFace"], item.fonts_added_by_ir)

    def test_missing_fonts_are_not_reported_as_a_match(self) -> None:
        # An empty font list means the PDF could not be read, not that it agreed.
        item = _comparison(ir_fonts=[])
        self.assertFalse(item.fonts_match)

    def test_text_is_measured_not_asserted(self) -> None:
        # The row never passes on its own: a difference in text is evidence for
        # a reviewer, not a verdict the harness can reach.
        item = _comparison(legacy_text="the same words", ir_text="the same words")
        self.assertFalse(item.text_matches)
        self.assertEqual([], item.text_lost)

    def test_a_missing_sentence_is_named(self) -> None:
        sentence = "This paragraph is long enough to be judged as a sentence."
        item = _comparison(legacy_text=sentence, ir_text="something else entirely")
        self.assertTrue(item.text_lost)

    def test_a_present_sentence_is_not_reported(self) -> None:
        sentence = "This paragraph is long enough to be judged as a sentence."
        item = _comparison(legacy_text=sentence, ir_text=sentence)
        self.assertEqual([], item.text_lost)

    def test_a_text_difference_is_reported_as_measurement(self) -> None:
        item = _comparison(ir_text="something else")
        self.assertFalse(item.text_matches)
        self.assertIsInstance(item.text_lost, list)

    def test_a_render_error_is_not_treated_as_success(self) -> None:
        item = _comparison(error="legacy render failed")
        self.assertFalse(item.ok)

    def test_ir_validation_errors_are_reported(self) -> None:
        item = _comparison(ir_errors=["DOC.IR.REF.BROKEN"])
        self.assertFalse(item.ok)

    def test_report_serialises_for_a_build_artifact(self) -> None:
        payload = _comparison().to_dict()
        json.dumps(payload)
        self.assertEqual(
            {"fixture", "genre", "language", "pages", "text", "fonts", "ir", "ok", "error"},
            set(payload),
        )


class ReportTextTests(TestCase):
    def test_the_report_explains_how_to_read_a_difference(self) -> None:
        text = shadow.render_text([_comparison(ir_pages=2)])
        # A bare "0/1 matched" invites the reader to assume the worst; the
        # report must say which dimension is decidable and which is measured.
        self.assertIn("pages", text)
        self.assertIn("fonts", text)
        self.assertIn("measured, never judged", text)

    def test_the_report_says_which_dimensions_are_decidable(self) -> None:
        text = shadow.render_text([_comparison(ir_pages=2)])
        self.assertIn("decidable", text)

    def test_the_report_counts_fixtures(self) -> None:
        text = shadow.render_text([_comparison()])
        self.assertIn("1/1", text)


class TemplateResolutionTests(TestCase):
    def test_language_selects_the_matching_template(self) -> None:
        zh = shadow._template_for({"genre": "one-pager", "language": "zh-Hans-CN"})
        en = shadow._template_for({"genre": "one-pager", "language": "en-US"})
        self.assertEqual("one-pager.html", zh.name)
        self.assertEqual("one-pager-en.html", en.name)

    def test_an_explicit_template_wins(self) -> None:
        chosen = shadow._template_for(
            {"genre": "changelog", "language": "en-US", "template": "changelog.html"}
        )
        self.assertEqual("changelog.html", chosen.name)


class LegacySubstitutionTests(TestCase):
    def test_both_key_forms_are_accepted(self) -> None:
        html = shadow._legacy_html("<p>{{A}}</p><p>{{B}}</p>", {"A": "one", "{{B}}": "two"})
        self.assertIn("one", html)
        self.assertIn("two", html)
        self.assertNotIn("{{", html)

    def test_an_unsupplied_placeholder_is_left_visible(self) -> None:
        # Leaving it visible is deliberate: a template rendering its own
        # instructional text is a fact about the run, not something to hide.
        html = shadow._legacy_html("<p>{{A}}</p>", {})
        self.assertIn("{{A}}", html)


class FixtureRunTests(TestCase):
    def test_a_real_fixture_compares_both_paths(self) -> None:
        import tempfile

        import corpus

        path = ROOT / "references" / "fixtures" / "document" / "canonical" / "canonical-zh-one-pager.yaml"
        if not path.is_file():
            self.skipTest("fixture not present")
        self.assertTrue(corpus.load_fixture(path))
        with tempfile.TemporaryDirectory() as tmp:
            result = shadow.compare_fixture(path, Path(tmp))
        self.assertIsNone(result.error, result.error)
        self.assertIsNotNone(result.legacy_pages)
        self.assertIsNotNone(result.ir_pages)
        self.assertGreater(result.ir_nodes, 0)
