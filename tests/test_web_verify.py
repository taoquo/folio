"""The browser's report judged against the page, not against the stylesheet.

These cases build the metric shape `web_measure.py` emits and check that each
rule fails the thing it names. They are the executable half of the composition
contract: prose that stops short of the column, a caption standing in the
margin and a label at 2.1:1 are failures here, whatever the CSS says.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_verify  # noqa: E402


def paragraph(**overrides) -> dict:
    base = {
        "index": 0,
        "role": "paragraph",
        "width": 760.0,
        "lines": {"count": 4, "widths": [560.0, 560.0, 560.0, 300.0],
                  "characters": 260, "han": 0},
    }
    base.update(overrides)
    return base


def caption(**overrides) -> dict:
    base = {
        "index": 0,
        "tag": "figcaption",
        "lines": {"count": 3, "widths": [180.0, 180.0, 120.0],
                  "characters": 80, "han": 0},
    }
    base.update(overrides)
    return base


class ColumnTests(unittest.TestCase):
    """The prose reaches the page's right edge; a narrower measure is a hole."""

    def _page(self, **overrides) -> dict:
        return {"paragraphs": [paragraph(**overrides)],
                "boxes": {"chapter": {"width": 760.0}}}

    def test_a_paragraph_narrower_than_the_column_fails(self) -> None:
        # 561px of prose inside a 760px column is the hole a measure cap
        # leaves: the text stops 200px short of the figures and the heading.
        page = self._page(width=561.0)
        self.assertEqual("FAIL", web_verify.check_column(page)["status"])

    def test_a_paragraph_that_reaches_the_column_passes(self) -> None:
        page = self._page(width=760.0)
        self.assertEqual("PASS", web_verify.check_column(page)["status"])

    def test_a_display_block_is_not_asked_for_the_column(self) -> None:
        # A pull quote's sentence is the quote's content, not running prose,
        # so the rule has nothing to judge rather than a narrow line to fail.
        page = self._page(width=420.0, role="quote")
        self.assertEqual("SKIP", web_verify.check_column(page)["status"])

    def test_a_page_without_a_column_is_skipped(self) -> None:
        page = {"paragraphs": [paragraph()]}
        self.assertEqual("SKIP", web_verify.check_column(page)["status"])


class CaptionTests(unittest.TestCase):
    """A caption belongs to the plate above it, and its left edge says so."""

    def test_a_caption_in_the_margin_fails(self) -> None:
        item = caption(left=56.0, plate_left=260.0, plate_width=660.0)
        self.assertEqual("FAIL", web_verify.check_captions({"captions": [item]})["status"])

    def test_a_caption_under_its_plate_passes(self) -> None:
        item = caption(left=260.0, plate_left=260.0, plate_width=660.0, width=660.0)
        self.assertEqual("PASS", web_verify.check_captions({"captions": [item]})["status"])

    def test_a_caption_wider_than_its_plate_fails(self) -> None:
        item = caption(left=260.0, plate_left=260.0, plate_width=660.0, width=760.0)
        self.assertEqual("FAIL", web_verify.check_captions({"captions": [item]})["status"])

    def test_a_page_without_captions_is_skipped(self) -> None:
        self.assertEqual("SKIP", web_verify.check_captions({})["status"])


class ContrastTests(unittest.TestCase):
    def test_black_on_white_is_the_maximum(self) -> None:
        ratio = web_verify.contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)")
        self.assertAlmostEqual(21.0, ratio or 0.0, places=1)

    def test_the_muted_grey_is_measured_not_assumed(self) -> None:
        ratio = web_verify.contrast_ratio("rgb(128, 128, 128)", "rgb(255, 255, 255)")
        self.assertAlmostEqual(3.95, ratio or 0.0, places=1)

    def test_a_role_below_its_ratio_fails(self) -> None:
        page = {"colours": {"caption-label": {
            "colour": "rgb(160, 160, 160)", "background": "rgb(255, 255, 255)",
            "size": 11, "weight": 400}}}
        row = web_verify.check_contrast(page)
        self.assertEqual("FAIL", row["status"])

    def test_a_large_numeral_may_use_the_large_text_floor(self) -> None:
        page = {"colours": {"chapter-numeral": {
            "colour": "rgb(130, 130, 130)", "background": "rgb(255, 255, 255)",
            "size": 44, "weight": 400}}}
        self.assertEqual("PASS", web_verify.check_contrast(page)["status"])

    def test_a_page_without_colour_roles_is_skipped(self) -> None:
        self.assertEqual("SKIP", web_verify.check_contrast({})["status"])


def plate(tiers: tuple[float, ...], framed: float = 300.0, band: float = 335.0) -> dict:
    return {"band": band, "view_box": [0, 0, framed, 400],
            "ink_box": [0, 0, framed, 400],
            "text_sizes": list(tiers), "title_units": 0}


class FigureTypeTests(unittest.TestCase):
    """V-FIG-12 judges every figure on the page, each on its own plate.

    The first implementation read the module's first manifest entry and the
    first visible plate, so a second figure could miss the floor on the
    strength of the first one's number.
    """

    def manifest(self, weak: bool = False) -> dict:
        return {"language": "en", "figures": {"m": {
            "first": {"variants": {"narrow": plate((8,))}},
            "second": {"variants": {"narrow": plate((6,) if weak else (8,))}},
        }}}

    def page(self) -> dict:
        return {"plates": [
            {"id": "first", "plates": 2,
             "visible": [{"variant": "narrow", "width": 335}]},
            {"id": "second", "plates": 2,
             "visible": [{"variant": "narrow", "width": 335}]},
        ]}

    def test_the_weak_figure_is_the_one_that_fails(self) -> None:
        row = web_verify.check_figure_type(
            self.manifest(weak=True), self.page(), "m", 390)
        self.assertEqual("FAIL", row["status"])
        self.assertIn("second[narrow]", row["detail"])

    def test_two_legible_plates_pass_together(self) -> None:
        row = web_verify.check_figure_type(self.manifest(), self.page(), "m", 390)
        self.assertEqual("PASS", row["status"])
        self.assertIn("2 plate(s)", row["detail"])

    def test_a_single_stage_family_is_reported_not_failed(self) -> None:
        manifest = self.manifest(weak=True)
        manifest["figures"]["m"]["second"]["single"] = True
        row = web_verify.check_figure_type(manifest, self.page(), "m", 390)
        self.assertEqual("REVIEW", row["status"])
        self.assertIn("composes on one stage", row["detail"])

    def test_a_figure_missing_from_the_manifest_fails(self) -> None:
        manifest = self.manifest()
        del manifest["figures"]["m"]["second"]
        row = web_verify.check_figure_type(manifest, self.page(), "m", 390)
        self.assertEqual("FAIL", row["status"])
        self.assertIn("not in the figure manifest", row["detail"])


if __name__ == "__main__":
    unittest.main()
