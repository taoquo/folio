"""The share card: what it renders, and what it refuses to emit.

The card is a build artifact, so the tests hold two things: the composition is
chosen by measurement (not by a constant), and the head block never states an
absolute address the build does not know.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import share_card as SC  # noqa: E402


def card(**overrides) -> SC.Card:
    values = {
        "kicker": "Document design system",
        "title": "Folio",
        "description": "Turn raw notes into stable artifacts, and reading pages.",
        "footer": "For documents worth keeping",
        "language": "en",
        "surface": "#F6F0EA",
        "ink": "#191514",
        "secondary": "#5A4A43",
        "muted": "#756A63",
        "accent": "#B83D2E",
    }
    values.update(overrides)
    return SC.Card(**values)


class UrlTests(unittest.TestCase):
    def test_a_directory_index_keeps_the_clean_url(self) -> None:
        self.assertEqual("https://example.com/", SC.page_url("https://example.com", ""))
        self.assertEqual("https://example.com/", SC.page_url("https://example.com", "index.html"))

    def test_any_other_page_keeps_its_path(self) -> None:
        self.assertEqual("https://example.com/index-zh.html",
                         SC.page_url("https://example.com", "/index-zh.html"))


class MetaTests(unittest.TestCase):
    def test_without_an_origin_no_absolute_tag_is_emitted(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.", url=None, image="share.png",
            image_alt="Folio", site="Folio", locale="en_US", kind="website")
        text = "\n".join(lines)
        for absent in ("og:url", "og:image", "canonical", "twitter:image"):
            self.assertNotIn(absent, text)
        self.assertIn('property="og:title"', text)

    def test_an_origin_makes_the_image_absolute(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.",
            url="https://example.com/attention/", image="share.png",
            image_alt="Folio", site="Folio", locale="en_US", kind="article")
        text = "\n".join(lines)
        self.assertIn('content="https://example.com/attention/share.png"', text)
        self.assertIn('href="https://example.com/attention/"', text)

    def test_the_version_makes_a_changed_card_a_changed_address(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.", url="https://example.com/",
            image="share.png", image_alt="Folio", site="Folio", locale="en_US",
            kind="website", version="936dc8b3")
        text = "\n".join(lines)
        self.assertEqual(2, text.count("share.png?v=936dc8b3"))
        self.assertNotIn("share.png\"", text)

    def test_no_version_leaves_the_address_alone(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.", url="https://example.com/",
            image="share.png", image_alt="Folio", site="Folio", locale="en_US",
            kind="website")
        self.assertNotIn("?v=", "\n".join(lines))

    def test_an_image_base_keeps_a_file_page_relative_to_the_site(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.",
            url="https://example.com/index-zh.html", image="assets/share.png",
            image_alt="Folio", site="Folio", locale="zh_CN", kind="website",
            image_base="https://example.com/")
        self.assertIn('content="https://example.com/assets/share.png"', "\n".join(lines))

    def test_a_page_that_owns_its_description_gets_no_second_one(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.", url=None, image=None,
            image_alt="Folio", site="Folio", locale="en_US", kind="website",
            with_description=False)
        self.assertFalse(any('name="description"' in line for line in lines))

    def test_the_theme_colour_is_the_surface(self) -> None:
        lines = SC.share_meta(
            title="Folio", description="A design system.", url=None, image=None,
            image_alt="Folio", site="Folio", locale="en_US", kind="website",
            theme_color="#F6F0EA")
        self.assertIn('<meta name="theme-color" content="#F6F0EA">', lines)


class TextTests(unittest.TestCase):
    def test_a_short_description_is_left_alone(self) -> None:
        self.assertEqual("Short.", SC.describe("Short."))

    def test_a_long_description_is_trimmed_at_a_boundary(self) -> None:
        text = "First sentence. " * 20
        trimmed = SC.describe(text)
        self.assertLessEqual(SC.display_width(trimmed), 160)
        self.assertTrue(text.startswith(trimmed.rstrip("…")))
        self.assertNotIn("….", trimmed)

    def test_cjk_counts_double(self) -> None:
        self.assertEqual(8, SC.display_width("文档设计"))

    def test_trim_prefers_a_sentence_boundary(self) -> None:
        self.assertEqual("First sentence.", SC.trim("First sentence. Second sentence.", 20))

    def test_trim_prefers_a_cjk_comma(self) -> None:
        self.assertEqual("把原始笔记…", SC.trim("把原始笔记，变成稳定的产物。", 8))


class StackTests(unittest.TestCase):
    def test_the_embedded_face_leads_the_page_stack(self) -> None:
        stack = SC.embedded_stack('"Charter", "Source Serif 4", Georgia, serif')
        self.assertTrue(stack.startswith('"Source Serif 4"'))
        self.assertIn("Charter", stack)

    def test_a_stack_that_already_leads_with_ours_is_unchanged(self) -> None:
        stack = '"Source Serif 4", "LXGW WenKai", Georgia, serif'
        self.assertEqual(stack, SC.embedded_stack(stack))


class PlateTests(unittest.TestCase):
    def test_a_portrait_plate_is_fitted_by_its_height(self) -> None:
        width, height = SC.plate_box('<svg viewBox="19 9 293 452"></svg>')
        self.assertAlmostEqual(SC.PLATE_BOTTOM - SC.PLATE_TOP, height, places=1)
        self.assertLessEqual(width, SC.PLATE_W)

    def test_a_wide_plate_is_fitted_by_its_width(self) -> None:
        width, height = SC.plate_box('<svg viewBox="0 0 900 200"></svg>')
        self.assertAlmostEqual(SC.PLATE_W, width, places=1)
        self.assertLess(height, SC.PLATE_BOTTOM - SC.PLATE_TOP)


class HeadBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = ('<!doctype html>\n<html><head>\n  <title>Folio</title>\n'
                     '  <meta name="description" content="A page.">\n</head><body></body></html>\n')
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "index.html"
        self.path.write_text(self.page, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_block_is_inserted_once_and_then_replaced(self) -> None:
        block = SC.meta_block(["<meta name=\"theme-color\" content=\"#fff\">"])
        ok, action = SC.apply_meta(self.path, block, check=False)
        self.assertTrue(ok)
        self.assertEqual("added", action)
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(1, text.count(SC.META_START))

        ok, action = SC.apply_meta(self.path, block, check=False)
        self.assertTrue(ok)
        self.assertEqual("matches", action)

    def test_a_check_reports_drift_without_writing(self) -> None:
        block = SC.meta_block(["<meta name=\"theme-color\" content=\"#fff\">"])
        SC.apply_meta(self.path, block, check=False)
        stale = SC.meta_block(["<meta name=\"theme-color\" content=\"#000\">"])
        ok, action = SC.apply_meta(self.path, stale, check=True)
        self.assertFalse(ok)
        self.assertEqual("differs", action)
        self.assertIn('content="#fff"', self.path.read_text(encoding="utf-8"))

    def test_a_canonical_is_rewritten_absolutely(self) -> None:
        stub = Path(self.tmp.name) / "index-en.html"
        stub.write_text('<link rel="canonical" href="./index.html">\n', encoding="utf-8")
        ok, _ = SC.apply_canonical(stub, "https://example.com/", check=False)
        self.assertTrue(ok)
        self.assertIn('href="https://example.com/"', stub.read_text(encoding="utf-8"))


def png_header(width: int, height: int) -> bytes:
    """A PNG signature and IHDR; enough for the size check, nothing to decode."""
    return (b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
            + width.to_bytes(4, "big") + height.to_bytes(4, "big"))


class CardFileTests(unittest.TestCase):
    def test_the_shipped_cards_are_the_advertised_size(self) -> None:
        for name in ("share-en.png", "share-zh.png"):
            self.assertEqual((1200, 630), SC.png_size(ROOT / "assets/images" / name))

    def test_a_file_that_is_not_a_png_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "share.png"
            path.write_bytes(b"not a png")
            with self.assertRaises(SC.ShareCardError):
                SC.png_size(path)


class SiteHeadTests(unittest.TestCase):
    """The portable half: the head must name the card that is on disk."""

    CSS = """
    :root {
      --color-surface-page: #F6F0EA;
      --color-text-primary: #191514;
      --color-text-secondary: #5A4A43;
      --color-text-muted: #756A63;
      --color-accent-brand: #B83D2E;
      --serif: Georgia, serif;
    }
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "styles.css").write_text(self.CSS, encoding="utf-8")
        (self.root / "index.html").write_text(
            '<!doctype html>\n<html><head>\n  <title>Folio</title>\n'
            '  <meta name="description" content="A design system.">\n'
            '</head><body></body></html>\n', encoding="utf-8")
        self.card = self.root / "share.png"
        self.card.write_bytes(png_header(1200, 630))
        self.data = {
            "site_name": "Folio",
            "origin": "https://example.com",
            "stylesheet": "styles.css",
            "manifest": "share.manifest.json",
            "pages": [{
                "file": "index.html", "out": "share.png", "path": "",
                "kicker": "Kicker", "title": "Folio",
                "description": "A design system.", "footer": "Footer",
                "language": "en", "image_alt": "Folio",
            }],
            "redirects": [],
        }
        self.config = self.root / "share.json"
        self.config.write_text(json.dumps(self.data), encoding="utf-8")
        self._root = SC.ROOT
        SC.ROOT = self.root

    def tearDown(self) -> None:
        SC.ROOT = self._root
        self.tmp.cleanup()

    def write_head(self) -> None:
        page = self.data["pages"][0]
        digest = hashlib.sha256(self.card.read_bytes()).hexdigest()[:8]
        lines = SC.site_meta(page, site="Folio", origin="https://example.com",
                             palette=SC.colours(self.CSS), version=digest)
        SC.apply_meta(self.root / "index.html", SC.meta_block(lines), check=False)

    def write_manifest(self) -> None:
        page = self.data["pages"][0]
        record = {
            "description": page["description"], "width": 1200, "height": 630,
            "sha256": hashlib.sha256(self.card.read_bytes()).hexdigest(),
            "title_px": 120, "lead_px": 26, "title_lines": 1, "lead_lines": 2,
            "lead_w": 900, "truncated": False,
        }
        (self.root / "share.manifest.json").write_text(
            SC.manifest_text([SC.site_record(page, record)]), encoding="utf-8")

    def test_a_head_that_names_the_card_passes(self) -> None:
        self.write_head()
        self.write_manifest()
        self.assertEqual(0, SC.site_cards(self.config, heads=True))

    def test_card_text_that_changed_without_a_redraw_fails(self) -> None:
        self.write_head()
        self.write_manifest()
        page = self.data["pages"][0]
        page["description"] = "A design system with a new sentence."
        self.config.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertEqual(1, SC.site_cards(self.config, heads=True))

    def test_a_card_that_changed_under_a_stale_head_fails(self) -> None:
        self.write_head()
        self.write_manifest()
        self.card.write_bytes(png_header(1200, 630) + b"\x00")
        self.assertEqual(1, SC.site_cards(self.config, heads=True))

    def test_a_card_of_the_wrong_size_fails(self) -> None:
        self.write_head()
        self.write_manifest()
        self.card.write_bytes(png_header(600, 315))
        self.assertEqual(1, SC.site_cards(self.config, heads=True))

    def test_a_missing_card_fails(self) -> None:
        self.card.unlink()
        self.assertEqual(1, SC.site_cards(self.config, heads=True))


@unittest.skipUnless(SC.available(), "pdftoppm is not installed")
class RenderTests(unittest.TestCase):
    """The artifact: a fixed size, a repeatable digest, ink inside the margins."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_two_renders_of_one_card_are_the_same_bytes(self) -> None:
        first = SC.render(card(), self.root / "a.png")
        second = SC.render(card(), self.root / "b.png")
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(1200, first["width"])
        self.assertEqual(630, first["height"])

    def test_the_ink_stays_inside_the_margins(self) -> None:
        record = SC.render(card(), self.root / "c.png")
        left, top, right, bottom = SC.ink_box(self.root / "c.png")
        self.assertGreaterEqual(left, SC.MARGIN_X - 4, record)
        self.assertLessEqual(right, 1200 - SC.MARGIN_X + 4, record)
        self.assertGreaterEqual(top, 32)
        self.assertLessEqual(bottom, 630 - 24)

    def test_a_long_title_drops_a_rung_instead_of_overflowing(self) -> None:
        long_title = "A title that has to wrap three times on a card of this size"
        record = SC.render(card(title=long_title), self.root / "d.png")
        self.assertLess(record["title_px"], SC.RUNGS[0][0])
        self.assertLessEqual(record["title_lines"], SC.MAX_TITLE_LINES)
        self.assertLessEqual(record["content_bottom"], SC.rule_top() - SC.CONTENT_GAP + 0.5)

    def test_the_record_says_what_the_fit_chose(self) -> None:
        record = SC.render(card(), self.root / "e.png")
        self.assertIn(record["title_px"], [title for title, _lead in SC.RUNGS])
        self.assertLessEqual(record["lead_w"], SC.LEAD_W)
        self.assertGreaterEqual(record["lead_w"], SC.LEAD_W_MIN)
        self.assertIn("description", record)


if __name__ == "__main__":
    unittest.main()
