"""Measurements must be honest about what could and could not be measured.

The inspector reports what a rendered page contains. It does not decide whether
that is good; thresholds belong to a contract.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artifact_inspector as ai


class WordGeometryTests(TestCase):
    def test_line_grouping_splits_on_vertical_distance(self) -> None:
        words = [
            ai.Word("first", 10, 10, 40, 20),
            ai.Word("line", 45, 10, 70, 20),
            ai.Word("second", 10, 40, 60, 50),
        ]
        lines = ai._group_lines(words, 1)
        self.assertEqual(2, len(lines))
        self.assertEqual("first line", lines[0].text)
        self.assertEqual("second", lines[1].text)

    def test_words_on_the_same_line_are_not_split(self) -> None:
        # A small baseline shift (superscript, inline code) must not break a line.
        words = [
            ai.Word("base", 10, 10, 40, 20),
            ai.Word("shifted", 45, 11.5, 80, 21.5),
        ]
        lines = ai._group_lines(words, 1)
        self.assertEqual(1, len(lines))

    def test_words_are_read_left_to_right(self) -> None:
        words = [ai.Word("world", 50, 10, 80, 20), ai.Word("hello", 10, 10, 45, 20)]
        lines = ai._group_lines(words, 1)
        self.assertEqual("hello world", lines[0].text)

    def test_hyphenated_line_is_detected(self) -> None:
        line = ai.Line(page=1, words=[ai.Word("hyphen-", 10, 10, 50, 20)], y=10, left=10, right=50)
        self.assertTrue(ai._is_hyphenated(line))

    def test_plain_line_is_not_hyphenated(self) -> None:
        line = ai.Line(page=1, words=[ai.Word("plain", 10, 10, 50, 20)], y=10, left=10, right=50)
        self.assertFalse(ai._is_hyphenated(line))


class StatisticsTests(TestCase):
    def test_mean_of_empty_is_none_not_zero(self) -> None:
        self.assertIsNone(ai._mean([]))

    def test_cv_needs_at_least_two_values(self) -> None:
        self.assertIsNone(ai._cv([1.0]))

    def test_cv_is_zero_for_identical_values(self) -> None:
        self.assertEqual(0.0, ai._cv([2.0, 2.0, 2.0]))

    def test_cv_grows_with_spread(self) -> None:
        tight = ai._cv([1.0, 1.01, 0.99])
        loose = ai._cv([1.0, 2.0, 0.5])
        self.assertLess(tight, loose)


class RealPdfTests(TestCase):
    def setUp(self) -> None:
        self.demo = ROOT / "assets" / "demos" / "demo-musk-resume.pdf"
        if not self.demo.is_file():
            self.skipTest("demo resume PDF not present")

    def test_inspection_extracts_the_document_shape(self) -> None:
        report = ai.inspect(self.demo)
        self.assertEqual(2, report.pages)
        self.assertGreater(report.lines, 50)
        self.assertGreater(report.words, 500)
        self.assertGreater(report.text_chars, 1000)

    def test_page_size_is_reported(self) -> None:
        report = ai.inspect(self.demo)
        self.assertIsNotNone(report.page_size)
        width, height = report.page_size
        self.assertAlmostEqual(595, width, delta=5)   # A4 width in points
        self.assertAlmostEqual(842, height, delta=5)  # A4 height in points

    def test_paragraph_count_is_plausible(self) -> None:
        report = ai.inspect(self.demo)
        self.assertGreater(report.paragraph_count, 5)
        self.assertLess(report.paragraph_count, report.lines)

    def test_text_block_height_is_derived_from_rendered_lines(self) -> None:
        # Fill ratio must be measurable without the caller supplying a height.
        report = ai.inspect(self.demo)
        self.assertIsNotNone(report.page_fill_cv)
        self.assertNotIn("text block height", report.unresolved)

    def test_page_fill_ratios_are_bounded(self) -> None:
        report = ai.inspect(self.demo)
        for ratio in report.page_fill_ratios:
            with self.subTest(ratio=ratio):
                self.assertGreaterEqual(ratio, 0.0)
                self.assertLessEqual(ratio, 1.0)

    def test_report_is_json_serializable(self) -> None:
        import json

        json.dumps(ai.inspect(self.demo).to_dict())

    def test_missing_file_is_reported_not_raised(self) -> None:
        report = ai.inspect(Path("/nonexistent/doc.pdf"))
        self.assertEqual(0, report.pages)
        self.assertTrue(report.notes)
