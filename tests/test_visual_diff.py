"""Visual comparison must be sensitive to real change and blind to noise.

SSIM is a regression signal only: it compares two renders of the same document
by the same renderer. Two renderers break lines differently by design, and that
is not a similarity failure.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import visual_diff as vd


class SsimInvariantTests(TestCase):
    """Properties that hold whatever the input image is."""

    def _image(self, pixels, size=(32, 32)):
        from PIL import Image

        img = Image.new("L", size)
        img.putdata(list(pixels))
        return img

    def _gradient(self, size=(32, 32)):
        import math

        width, height = size
        data = [int(255 * (math.sin(x / 5) + 1) / 2) for y in range(height) for x in range(width)]
        return self._image(data, size)

    def test_identical_images_score_one(self) -> None:
        img = self._gradient()
        self.assertAlmostEqual(1.0, vd.ssim(img, img), places=6)

    def test_identical_images_have_no_changed_pixels(self) -> None:
        img = self._gradient()
        self.assertEqual(0.0, vd.changed_pixel_ratio(img, img))

    def test_unrelated_images_score_far_below_one(self) -> None:
        from PIL import Image

        white = Image.new("L", (32, 32), 255)
        pattern = self._gradient()
        self.assertLess(vd.ssim(white, pattern), 0.5)

    def test_unrelated_images_report_changed_pixels(self) -> None:
        from PIL import Image

        white = Image.new("L", (32, 32), 255)
        black = Image.new("L", (32, 32), 0)
        self.assertGreater(vd.changed_pixel_ratio(white, black), 0.9)

    def test_score_never_exceeds_one(self) -> None:
        # Clamping matters: a regression gate that can report 1.0001 is noise.
        from PIL import Image

        a = Image.new("L", (16, 16), 100)
        b = Image.new("L", (16, 16), 101)
        self.assertLessEqual(vd.ssim(a, b), 1.0)

    def test_pixel_threshold_ignores_subtle_noise(self) -> None:
        from PIL import Image

        a = Image.new("L", (16, 16), 128)
        b = Image.new("L", (16, 16), 132)  # 4 levels: below the threshold of 8
        self.assertEqual(0.0, vd.changed_pixel_ratio(a, b))

    def test_pixel_threshold_counts_visible_change(self) -> None:
        from PIL import Image

        a = Image.new("L", (16, 16), 128)
        b = Image.new("L", (16, 16), 200)  # 72 levels: clearly visible
        self.assertGreater(vd.changed_pixel_ratio(a, b), 0.5)


class ThresholdGateTests(TestCase):
    """The comparison runs end-to-end against real rendered files."""

    def setUp(self) -> None:
        self.demo = ROOT / "assets" / "demos" / "demo-musk-resume.pdf"
        if not self.demo.is_file():
            self.skipTest("demo resume PDF not present")

    def test_a_file_compared_with_itself_matches(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = vd.compare_pdfs(self.demo, self.demo, 100, Path(tmp))
        summary = report.summary()
        self.assertEqual(1.0, summary["ssim_median"])
        self.assertEqual(0.0, summary["changed_ratio_max"])
        self.assertEqual(0, summary["pages_missing"])

    def test_comparison_detects_differing_documents(self) -> None:
        other = ROOT / "assets" / "demos" / "demo-tesla.pdf"
        if not other.is_file():
            self.skipTest("second demo PDF not present")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = vd.compare_pdfs(self.demo, other, 100, Path(tmp))
        summary = report.summary()
        self.assertIsNotNone(summary["ssim_median"])
        self.assertLess(summary["ssim_median"], 0.9)

    def test_page_count_difference_is_reported(self) -> None:
        other = ROOT / "assets" / "demos" / "demo-tesla.pdf"
        if not other.is_file():
            self.skipTest("second demo PDF not present")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = vd.compare_pdfs(self.demo, other, 100, Path(tmp))
        # One document has more pages than the other, so at least one page is
        # reported missing rather than silently ignored.
        self.assertGreater(report.summary()["pages_missing"], 0)

    def test_missing_file_is_noted_rather_than_crashing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = vd.compare_pdfs(Path("/nonexistent/a.pdf"), self.demo, 100, Path(tmp))
        self.assertTrue(report.notes)
        self.assertEqual([], report.comparable)

    def test_report_is_json_serializable(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = vd.compare_pdfs(self.demo, self.demo, 100, Path(tmp))
        json.dumps(report.to_dict())


class RasterisationTests(TestCase):
    def test_rasterising_produces_one_image_per_page(self) -> None:
        import tempfile

        pdf = ROOT / "assets" / "demos" / "demo-musk-resume.pdf"
        if not pdf.is_file():
            self.skipTest("demo resume PDF not present")
        with tempfile.TemporaryDirectory() as tmp:
            pages = vd.rasterise(pdf, Path(tmp), 72)
        self.assertEqual(2, len(pages))
