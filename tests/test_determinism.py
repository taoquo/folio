"""Rendering the same source twice must produce the same visible page.

PDF bytes are not the signal: WeasyPrint's zlib streams differ between
processes while the rendered page is identical. These tests pin the
content-level comparison and the fresh-process render that makes it meaningful.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import determinism


def _result(**kwargs):
    base = {"target": "t", "source": "t.html", "repeats": 3}
    base.update(kwargs)
    return determinism.DeterminismResult(**base)


class DeterminismVerdictTests(TestCase):
    def test_identical_content_is_deterministic(self) -> None:
        result = _result(
            pages=[2, 2, 2],
            fonts=[["Charter"], ["Charter"], ["Charter"]],
            rasters=["r", "r", "r"],
            texts=["t", "t", "t"],
            pdf_digests=["a", "b", "c"],
        )
        self.assertTrue(result.deterministic)

    def test_varying_pdf_bytes_alone_is_not_a_failure(self) -> None:
        # This is the real behaviour of WeasyPrint: same page, different stream.
        result = _result(
            pages=[7, 7, 7],
            fonts=[["Charter"]] * 3,
            rasters=["r"] * 3,
            texts=["t"] * 3,
            pdf_digests=["a", "b", "c"],
        )
        self.assertTrue(result.deterministic)
        self.assertFalse(result.byte_stable)

    def test_pdf_bytes_matching_is_reported_as_byte_stable(self) -> None:
        result = _result(
            pages=[1, 1],
            fonts=[["Charter"]] * 2,
            rasters=["r"] * 2,
            texts=["t"] * 2,
            pdf_digests=["a", "a"],
        )
        self.assertTrue(result.byte_stable)

    def test_page_count_drift_is_a_failure(self) -> None:
        result = _result(
            pages=[2, 3, 2],
            fonts=[["Charter"]] * 3,
            rasters=["r"] * 3,
            texts=["t"] * 3,
            pdf_digests=["a"] * 3,
        )
        self.assertFalse(result.deterministic)
        self.assertIn("pages", result.unstable_signals())

    def test_raster_drift_is_a_failure(self) -> None:
        result = _result(
            pages=[2, 2, 2],
            fonts=[["Charter"]] * 3,
            rasters=["r", "different", "r"],
            texts=["t"] * 3,
            pdf_digests=["a"] * 3,
        )
        self.assertFalse(result.deterministic)
        self.assertEqual(["raster"], result.unstable_signals())

    def test_text_drift_is_a_failure(self) -> None:
        result = _result(
            pages=[2, 2, 2],
            fonts=[["Charter"]] * 3,
            rasters=["r"] * 3,
            texts=["t", "t", "other"],
            pdf_digests=["a"] * 3,
        )
        self.assertFalse(result.deterministic)
        self.assertEqual(["text"], result.unstable_signals())

    def test_font_drift_is_a_failure(self) -> None:
        result = _result(
            pages=[2, 2, 2],
            fonts=[["Charter"], ["Georgia"], ["Charter"]],
            rasters=["r"] * 3,
            texts=["t"] * 3,
            pdf_digests=["a"] * 3,
        )
        self.assertFalse(result.deterministic)
        self.assertEqual(["fonts"], result.unstable_signals())

    def test_a_single_observation_proves_nothing(self) -> None:
        result = _result(pages=[2], fonts=[["Charter"]], rasters=["r"], texts=["t"])
        self.assertFalse(result.deterministic)

    def test_render_error_is_reported_not_treated_as_success(self) -> None:
        self.assertFalse(_result(error="RuntimeError: render failed").deterministic)

    def test_serialization_is_json_safe(self) -> None:
        result = _result(
            pages=[1, 1],
            fonts=[["Charter"]] * 2,
            rasters=["r"] * 2,
            texts=["t"] * 2,
            pdf_digests=["f" * 64] * 2,
        )
        payload = result.to_dict()
        json.dumps(payload)
        self.assertEqual(["f" * 16, "f" * 16], payload["pdf_digests"])

    def test_unknown_target_is_rejected_before_rendering(self) -> None:
        self.assertEqual(2, determinism.main(["--repeat", "2", "no-such-target"]))

    def test_pptx_target_is_not_accepted_as_an_html_target(self) -> None:
        self.assertEqual(2, determinism.main(["--repeat", "2", "slides"]))

    def test_repeat_below_two_is_rejected(self) -> None:
        self.assertEqual(2, determinism.main(["--repeat", "1", "resume-en"]))

    def test_every_html_contract_target_is_checkable(self) -> None:
        from page_contracts import HTML_TARGETS

        for target, spec in HTML_TARGETS.items():
            with self.subTest(target=target):
                self.assertTrue((determinism.TEMPLATES / spec.source).is_file())


class FreshProcessRenderingTests(TestCase):
    def test_rendering_uses_a_separate_process(self) -> None:
        # In-process repeats measure caching, not reproducibility.
        self.assertIn("weasyprint", determinism._RENDER_CHILD)
        self.assertIn("sys.argv[1]", determinism._RENDER_CHILD)
