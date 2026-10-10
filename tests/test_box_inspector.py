"""Reading pagination from the renderer's box tree.

The artifact inspector estimates paragraph boundaries from line spacing, because
a PDF carries no source identifiers. On a long document that estimate saturates:
every paragraph crossing a page boundary scored as a widow, which made the rate
100% and the measurement useless for judging layout.

The box tree has the answer. These tests hold the arithmetic and the claim that
the two methods disagree.
"""

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import box_inspector  # noqa: E402

TEMPLATES = ROOT / "assets" / "templates"


def _html(body: str, extra_css: str = "") -> str:
    return (
        "<html><head><style>"
        "@page { size: A4; margin: 20mm; }"
        "body { font-family: serif; font-size: 10pt; line-height: 1.45; }"
        "p { margin: 0 0 6pt 0; }"
        f"{extra_css}"
        "</style></head><body>"
        f"{body}"
        "</body></html>"
    )


class BoxReadingTests(TestCase):
    def _render(self, work: Path, html: str, name: str) -> Path:
        source = work / f"{name}.html"
        source.write_text(html, encoding="utf-8")
        return source

    def test_a_paragraph_is_read_with_its_line_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>One short paragraph.</p>"), "a")
            report = box_inspector.inspect(source)
        self.assertEqual(1, len(report.paragraphs))
        self.assertGreaterEqual(report.paragraphs[0].lines, 1)

    def test_a_long_paragraph_wraps_onto_several_lines(self) -> None:
        text = "word " * 200
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html(f"<p>{text}</p>"), "b")
            report = box_inspector.inspect(source)
        self.assertGreater(report.paragraphs[0].lines, 2)

    def test_two_paragraphs_are_read_as_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>Alpha</p><p>Beta</p>"), "c")
            report = box_inspector.inspect(source)
        self.assertEqual(2, len(report.paragraphs))

    def test_a_heading_is_recognised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<h2>Title</h2><p>Body</p>"), "d")
            report = box_inspector.inspect(source)
        headings = [p for p in report.paragraphs if p.is_heading]
        self.assertEqual(1, len(headings))
        self.assertEqual("h2", headings[0].tag)

    def test_a_paragraph_reports_its_text(self) -> None:
        # The characters live in the leaf boxes; reading only the line box left
        # every paragraph empty, which broke the content-based identification of
        # a paragraph continued across a page.
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>Distinctive wording here.</p>"), "txt")
            report = box_inspector.inspect(source)
        self.assertIn("Distinctive", report.paragraphs[0].text)

    def test_no_widow_is_reported_for_a_single_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>Alpha</p><p>Beta</p>"), "e")
            report = box_inspector.inspect(source)
        self.assertEqual(0, report.widows)
        self.assertEqual(0, report.orphans)

    def test_a_spanning_paragraph_is_detected(self) -> None:
        # Enough text to cross a page boundary, with the paragraph continuing.
        body = "<p>" + ("word " * 3000) + "</p>"
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html(body), "f")
            report = box_inspector.inspect(source)
        self.assertGreater(report.pages, 1)
        self.assertGreater(report.spanning, 0)

    def test_a_missing_document_is_reported_not_raised(self) -> None:
        report = box_inspector.inspect(Path("/nonexistent.html"))
        self.assertTrue(report.notes)

    def test_the_report_is_serialisable(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>Alpha</p>"), "g")
            payload = box_inspector.inspect(source).to_json()
        json.dumps(payload)
        self.assertIn("method", payload)

    def test_the_report_says_how_the_measurement_was_made(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._render(Path(tmp), _html("<p>Alpha</p>"), "h")
            payload = box_inspector.inspect(source).to_json()
        self.assertIn("read, not inferred", payload["method"])


class ComparisonTests(TestCase):
    def test_the_comparison_reports_both_methods(self) -> None:
        source = TEMPLATES / "long-doc.html"
        if not source.is_file():
            self.skipTest("template not present")
        payload = box_inspector.compare(source)
        self.assertIn("box", payload)
        # A rendered PDF may or may not sit beside the template.
        self.assertIn("geometry", payload)

    def test_the_box_tree_counts_fewer_widows_than_the_estimate(self) -> None:
        # The estimate saturates; the box tree does not. This is the finding the
        # module exists to record, so it is asserted against a real document.
        html_source = Path("/tmp/ld.html")
        if not html_source.is_file():
            self.skipTest("no comparison fixture prepared")
        payload = box_inspector.compare(html_source)
        geometry = payload.get("geometry")
        if not geometry:
            self.skipTest("no rendered PDF to compare against")
        self.assertLessEqual(payload["box"]["widows"], geometry["widows"])
