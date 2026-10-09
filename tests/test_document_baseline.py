"""A baseline is a reviewed decision, not a way to make CI green.

These tests pin the governance the diagram catalog already established: an
approval reason is mandatory, a tampered reference is detected, and comparison
uses what the reader sees rather than unstable PDF bytes.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import document_baseline as db


def _record(target="one-pager", **overrides):
    record = {
        "target": target,
        "source": f"{target}.html",
        "kind": "pdf",
        "pages": 1,
        "pdf_sha256": "a" * 64,
        "pdf_bytes": 1000,
        "fonts": ["RATJMB+Charter"],
        "metadata": {"Producer": "Folio"},
        "preview_sha256": "p" * 64,
        "preview_bytes": 5000,
        "text_sha256": "t" * 64,
        "text_excerpt": "Hello",
        "error": None,
    }
    record.update(overrides)
    return record


def _capture(*records, dpi=160):
    return {"schema_version": db.SCHEMA_VERSION, "raster_dpi": dpi, "targets": list(records)}


def _baseline(*records, dpi=160, **overrides):
    payload = {
        "schema_version": db.SCHEMA_VERSION,
        "approval_state": "approved",
        "approval_reason": "reviewed",
        "raster_dpi": dpi,
        "targets": list(records),
    }
    payload.update(overrides)
    return payload


class BaselineGovernanceTests(TestCase):
    def test_matching_capture_reports_match(self) -> None:
        report = db.compare_baseline(_capture(_record()), _baseline(_record()))
        self.assertEqual("match", report["status"])
        self.assertEqual([], report["differences"])

    def test_missing_approval_reason_is_an_issue(self) -> None:
        report = db.compare_baseline(_capture(_record()), _baseline(_record(), approval_reason="   "))
        self.assertEqual("different", report["status"])
        self.assertTrue(any("approval reason" in i for i in report["issues"]))

    def test_unapproved_state_is_an_issue(self) -> None:
        report = db.compare_baseline(_capture(_record()), _baseline(_record(), approval_state="draft"))
        self.assertTrue(any("approved" in i for i in report["issues"]))

    def test_schema_version_mismatch_is_an_issue(self) -> None:
        report = db.compare_baseline(_capture(_record()), _baseline(_record(), schema_version="0.9"))
        self.assertTrue(any("schema_version" in i for i in report["issues"]))

    def test_raster_dpi_mismatch_is_an_issue(self) -> None:
        # Comparing captures taken at different DPI would produce phantom diffs.
        report = db.compare_baseline(_capture(_record(), dpi=300), _baseline(_record(), dpi=160))
        self.assertTrue(any("DPI" in i for i in report["issues"]))

    def test_missing_target_is_reported(self) -> None:
        report = db.compare_baseline(_capture(), _baseline(_record()))
        self.assertTrue(any("missing from capture" in i for i in report["issues"]))

    def test_new_target_is_reported_as_unapproved(self) -> None:
        report = db.compare_baseline(_capture(_record(), _record("resume")), _baseline(_record()))
        self.assertTrue(any("unapproved target" in i for i in report["issues"]))


class BaselineDifferenceTests(TestCase):
    def _diff(self, after, before=None):
        before = before or _record()
        return db.compare_baseline(_capture(after), _baseline(before))

    def test_pdf_byte_change_alone_is_not_a_difference(self) -> None:
        # zlib compression is not stable across processes; the page is.
        report = self._diff(_record(pdf_sha256="b" * 64, pdf_bytes=1200))
        self.assertEqual("match", report["status"])

    def test_page_count_change_is_detected(self) -> None:
        report = self._diff(_record(pages=2))
        self.assertEqual("different", report["status"])
        self.assertIn("pages", report["differences"][0]["changed"])

    def test_font_change_is_detected(self) -> None:
        report = self._diff(_record(fonts=["RATJMB+Georgia"]))
        self.assertIn("fonts", report["differences"][0]["changed"])

    def test_raster_change_is_detected(self) -> None:
        report = self._diff(_record(preview_sha256="q" * 64))
        self.assertIn("preview_sha256", report["differences"][0]["changed"])

    def test_text_change_is_detected(self) -> None:
        report = self._diff(_record(text_sha256="u" * 64))
        self.assertIn("text_sha256", report["differences"][0]["changed"])

    def test_difference_records_before_and_after(self) -> None:
        report = self._diff(_record(pages=2))
        entry = report["differences"][0]
        self.assertEqual(1, entry["pages_before"])
        self.assertEqual(2, entry["pages_after"])

    def test_render_error_is_surfaced(self) -> None:
        report = self._diff(_record(error="RuntimeError: boom", pages=None))
        self.assertEqual("different", report["status"])
        self.assertIn("render-error", report["differences"][0]["changed"])


class BaselineWriteTests(TestCase):
    def test_write_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            db._write_baseline(_capture(_record()), "   ", 160)

    def test_write_persists_coverage_and_reason(self) -> None:
        original = db.BASELINE_FILE
        original_dir = db.BASELINE_DIR
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db.BASELINE_DIR = Path(tmp)
            db.BASELINE_FILE = Path(tmp) / "baseline.json"
            try:
                path = db._write_baseline(_capture(_record()), "approved for test", 160)
                payload = json.loads(path.read_text(encoding="utf-8"))
            finally:
                db.BASELINE_DIR = original_dir
                db.BASELINE_FILE = original

        self.assertEqual("approved", payload["approval_state"])
        self.assertEqual("approved for test", payload["approval_reason"])
        self.assertEqual(160, payload["raster_dpi"])
        self.assertEqual(1, payload["coverage"]["captured"])

    def test_capture_refuses_to_write_without_a_reason(self) -> None:
        # Without --approval-reason the capture must not silently become the
        # approved baseline; it is rejected outright.
        original = db.BASELINE_FILE
        original_dir = db.BASELINE_DIR
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db.BASELINE_DIR = Path(tmp)
            db.BASELINE_FILE = Path(tmp) / "baseline.json"
            try:
                code = db.main(["capture", "--no-preview"])
                written = db.BASELINE_FILE.exists()
            finally:
                db.BASELINE_DIR = original_dir
                db.BASELINE_FILE = original

        self.assertEqual(2, code)
        self.assertFalse(written, "no baseline should be written without a reason")


class BaselineCoverageTests(TestCase):
    def test_baseline_covers_every_registered_target(self) -> None:
        if not db.BASELINE_FILE.is_file():
            self.skipTest("no baseline captured yet")
        payload = json.loads(db.BASELINE_FILE.read_text(encoding="utf-8"))
        from page_contracts import HTML_TARGETS, PPTX_TARGETS

        expected = set(HTML_TARGETS) | set(PPTX_TARGETS)
        recorded = {t["target"] for t in payload["targets"]}
        self.assertEqual(expected, recorded)

    def test_every_recorded_target_rendered_without_error(self) -> None:
        if not db.BASELINE_FILE.is_file():
            self.skipTest("no baseline captured yet")
        payload = json.loads(db.BASELINE_FILE.read_text(encoding="utf-8"))
        for entry in payload["targets"]:
            with self.subTest(target=entry["target"]):
                self.assertIsNone(entry["error"])

    def test_html_records_carry_content_signals(self) -> None:
        if not db.BASELINE_FILE.is_file():
            self.skipTest("no baseline captured yet")
        payload = json.loads(db.BASELINE_FILE.read_text(encoding="utf-8"))
        for entry in payload["targets"]:
            if entry["kind"] != "pdf":
                continue
            with self.subTest(target=entry["target"]):
                self.assertIsNotNone(entry["pages"])
                self.assertTrue(entry["preview_sha256"], "raster digest should be recorded")
                self.assertTrue(entry["text_sha256"], "text digest should be recorded")
