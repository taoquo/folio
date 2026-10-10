"""Quality is a vector, never a single score.

A collapsed number hides trade-offs: a document can gain even line texture and
lose page balance at the same time. These tests pin the separation between
correctness (a gate) and craft (a report), and pin the refusal to invent
certainty where nothing could be measured.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import quality_vector as qv
from artifact_inspector import InspectorReport


def _report(**overrides) -> InspectorReport:
    base = {
        "path": "doc.pdf",
        "pages": 2,
        "page_size": (595.0, 842.0),
        "fonts": ["RATJMB+Source-Serif-4"],
        "lines": 76,
        "words": 847,
        "text_chars": 4801,
        "paragraph_count": 20,
        "hyphenated_line_count": 1,
        "max_consecutive_hyphens": 1,
        "short_last_line_count": 2,
        "last_line_ratios": [0.42] * 18,
        "line_fill_ratios": [0.70] * 76,
        "page_line_counts": [42, 34],
        "page_fill_ratios": [0.9, 0.88],
        "page_fill_cv": 0.01,
    }
    base.update(overrides)
    return InspectorReport(**base)


class NoSingleScoreTests(TestCase):
    def test_the_vector_has_no_overall_score(self) -> None:
        vector = qv.QualityVector(path="doc.pdf")
        payload = vector.to_dict()
        self.assertNotIn("score", payload)
        for key in payload:
            self.assertNotIn("quality_score", key)

    def test_dimensions_are_reported_separately(self) -> None:
        report = _report()
        vector = qv.QualityVector(path="doc.pdf")
        vector.add(qv.typography_dimension(report, qv.DEFAULTS))
        vector.add(qv.pagination_dimension(report, qv.DEFAULTS))
        self.assertEqual({"typography", "pagination"}, {d.name for d in vector.dimensions})


class CorrectnessGateTests(TestCase):
    """Correctness failures must fail; craft concerns must not."""

    def test_page_count_outside_contract_fails(self) -> None:
        dimension = qv.correctness_dimension(_report(pages=3), expected_pages=(2, 2))
        self.assertEqual("FAIL", dimension.status)
        self.assertEqual("correctness", dimension.gate)

    def test_page_count_inside_contract_passes(self) -> None:
        dimension = qv.correctness_dimension(_report(pages=2), expected_pages=(2, 2))
        self.assertEqual("PASS", dimension.status)

    def test_a_document_with_no_pages_fails(self) -> None:
        dimension = qv.correctness_dimension(_report(pages=0), expected_pages=None)
        self.assertEqual("FAIL", dimension.status)

    def test_typography_concerns_never_fail_the_gate(self) -> None:
        # Even a badly ragged document is a review item, not a broken build.
        report = _report(short_last_line_count=18, paragraph_count=20,
                         last_line_ratios=[0.05] * 18, max_consecutive_hyphens=9)
        dimension = qv.typography_dimension(report, qv.DEFAULTS)
        self.assertIn(dimension.status, {"PASS", "REVIEW"})
        self.assertNotEqual("FAIL", dimension.status)

    def test_pagination_concerns_never_fail_the_gate(self) -> None:
        report = _report(page_fill_cv=0.9)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertNotEqual("FAIL", dimension.status)

    def test_missing_text_fails_accessibility(self) -> None:
        dimension = qv.accessibility_dimension(_report(text_chars=0))
        self.assertEqual("FAIL", dimension.status)
        self.assertEqual("correctness", dimension.gate)


class MeasurementHonestyTests(TestCase):
    """Unmeasured is reported as unmeasured, never as zero."""

    def test_unresolved_metrics_produce_a_review(self) -> None:
        dimension = qv.unresolved_dimension(_report(unresolved=["line measure"]))
        self.assertEqual("REVIEW", dimension.status)
        self.assertEqual(["line measure"], dimension.metrics["unresolved"])

    def test_nothing_unresolved_passes(self) -> None:
        dimension = qv.unresolved_dimension(_report(unresolved=[]))
        self.assertEqual("PASS", dimension.status)

    def test_page_fill_absent_is_review_not_failure(self) -> None:
        report = _report(page_fill_cv=None)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual("REVIEW", dimension.status)


class PaginationSignalTests(TestCase):
    def test_a_thin_page_among_full_ones_is_flagged(self) -> None:
        report = _report(page_line_counts=[40, 40, 5], pages=3)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual([3], dimension.metrics["thin_pages"])

    def test_evenly_filled_pages_are_not_flagged(self) -> None:
        report = _report(page_line_counts=[40, 38, 39], pages=3)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual([], dimension.metrics["thin_pages"])


class SerializationTests(TestCase):
    def test_vector_is_json_serializable(self) -> None:
        report = _report()
        vector = qv.QualityVector(path="doc.pdf", genre="resume")
        vector.add(qv.correctness_dimension(report, (2, 2)))
        vector.add(qv.typography_dimension(report, qv.DEFAULTS))
        vector.add(qv.pagination_dimension(report, qv.DEFAULTS))
        vector.add(qv.accessibility_dimension(report))
        vector.add(qv.unresolved_dimension(report))
        payload = vector.to_dict()
        json.dumps(payload)
        self.assertEqual([], payload["correctness_failures"])

    def test_thresholds_are_declared_in_one_place(self) -> None:
        # A threshold invented at a call site cannot be calibrated later.
        for key in ("last_line_ratio_min", "short_last_line_rate_max",
                    "consecutive_hyphens_max", "page_fill_cv_max"):
            with self.subTest(threshold=key):
                self.assertIn(key, qv.DEFAULTS)


class RealDocumentTests(TestCase):
    def test_a_rendered_demo_produces_a_vector(self) -> None:
        demo = ROOT / "assets" / "demos" / "demo-musk-resume.pdf"
        if not demo.is_file():
            self.skipTest("demo resume PDF not present")
        try:
            import build

            manifest = build.load_font_manifest()
        except Exception:
            manifest = {}
        vector = qv.evaluate(demo, "resume-en", qv.DEFAULTS, manifest)
        names = {d.name for d in vector.dimensions}
        self.assertEqual(
            {
                "correctness", "typography", "pagination", "visual_rhythm",
                "readability", "accessibility", "pdf_ua", "renderer_stability",
                "reproducibility", "measurement",
            },
            names,
        )
        self.assertEqual([], vector.correctness_failures)


class SinglePageSemanticsTests(TestCase):
    """One page has nothing to balance against; that is not a finding."""

    def test_single_page_passes_pagination(self) -> None:
        report = _report(pages=1, page_line_counts=[30], page_fill_cv=None)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual("PASS", dimension.status)
        self.assertTrue(dimension.metrics.get("single_page"))

    def test_multi_page_without_variance_data_is_reviewed(self) -> None:
        report = _report(pages=3, page_line_counts=[30, 28, 29], page_fill_cv=None)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual("REVIEW", dimension.status)

    def test_unbalanced_multi_page_is_reviewed(self) -> None:
        report = _report(pages=3, page_line_counts=[40, 40, 38], page_fill_cv=0.9)
        dimension = qv.pagination_dimension(report, qv.DEFAULTS)
        self.assertEqual("REVIEW", dimension.status)
