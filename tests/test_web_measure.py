"""The Web page is measured by a browser, not by the print renderer.

Two facts are pinned here. First, WeasyPrint cannot be the screen oracle: it
does not evaluate width media queries, so a page measured with it would report
the desktop layer at every viewport. Second, when a Chromium build is available,
the measurement reads the responsive layer the way a reader sees it.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURE = ROOT / "references" / "fixtures" / "web" / "reading-demo"


class PrintRendererCannotMeasureScreenMedia(unittest.TestCase):
    """WeasyPrint is a print formatter and stays one."""

    def test_width_media_queries_do_not_apply(self) -> None:
        from weasyprint import HTML

        html = """
        <html><head><style>
          @page { size: 390px 800px; margin: 0 }
          p { font-size: 16px }
          @media (max-width: 5000px) { p { font-size: 10px } }
        </style></head><body><p>x</p></body></html>
        """
        document = HTML(string=html).render(media_type="screen")
        sizes: list[float] = []

        def walk(box) -> None:
            if getattr(box, "element_tag", None) == "p":
                sizes.append(float(box.style["font_size"]))
            for child in getattr(box, "children", None) or []:
                walk(child)

        walk(document.pages[0]._page_box)
        self.assertTrue(sizes)
        self.assertEqual({16.0}, set(sizes))


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        import web_measure

        with sync_playwright() as p:
            browser = web_measure.launch(p)
            browser.close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_browser_available(), "no Chromium/Chrome build for Playwright")
class BrowserMeasurementTests(unittest.TestCase):
    """The measurement sees the responsive layer, at the widths it is given."""

    @classmethod
    def setUpClass(cls) -> None:
        import build_web
        import web_measure

        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls.tmp.name)
        build_web.build(FIXTURE, cls.dist, None)
        cls.result = web_measure.measure(cls.dist, "reading-demo", (390, 1414))
        cls.module = next(
            viewports for name, viewports in cls.result["pages"].items()
            if name.count("/") == 2
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_the_phone_width_gets_the_narrow_type_scale(self) -> None:
        page = self.module["390"]
        self.assertEqual(16, page["types"]["body"]["size"])
        self.assertEqual(32, page["types"]["h1"]["size"])
        self.assertEqual(page["boxes"]["prose"]["width"], page["boxes"]["figure-svg"]["width"])

    def test_the_wide_width_widens_the_column(self) -> None:
        page = self.module["1414"]
        self.assertEqual(48, page["types"]["h1"]["size"])
        self.assertGreater(page["boxes"]["prose"]["width"], 700)

    def test_an_intended_scroll_container_is_not_reported_as_overflow(self) -> None:
        for name, viewports in self.result["pages"].items():
            for width, metrics in viewports.items():
                with self.subTest(page=name, width=width):
                    self.assertEqual([], metrics["overflow"])


@unittest.skipUnless(_browser_available(), "no Chromium/Chrome build for Playwright")
class PlanMatchesRenderTests(unittest.TestCase):
    """The page computes what its plan says. This is invariant I3, end to end."""

    @classmethod
    def setUpClass(cls) -> None:
        import build_web
        import web_measure

        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls.tmp.name)
        build_web.build(FIXTURE, cls.dist, None)
        cls.plan = json.loads(
            (cls.dist / "reading-demo" / "plan.json").read_text(encoding="utf-8"))
        cls.metrics = web_measure.measure(cls.dist, "reading-demo", (390, 768, 1414))
        cls.manifest = json.loads(
            (cls.dist / "reading-demo" / "figures.manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_no_verification_rule_fails(self) -> None:
        import web_verify

        rows = web_verify.summarise(
            web_verify.verify(self.plan, self.metrics, self.manifest))
        failed = [row for row in rows if row["status"] == "FAIL"]
        self.assertEqual([], failed, rows)

    def test_the_measured_widths_are_widths_the_plan_states(self) -> None:
        for width in (390, 768, 1414):
            with self.subTest(width=width):
                self.assertIn(str(width), self.plan["viewports"])


if __name__ == "__main__":
    unittest.main()
