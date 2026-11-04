"""The page model: what is on the page, and that nothing else is.

The model is the layer the fragment never had. These tests hold it to three
promises: it reads only top-level blocks, it refuses anything it cannot name,
and annotating the source changes no text.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_page as WP  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / ".." / "references" / "fixtures" / "web"
FRAGMENT = FIXTURE / "reading-demo" / "reading.frag.html"


def chapter(body: str, ident: str = "s01", summary: str = "summary") -> str:
    return (f'<section class="chapter" id="{ident}" data-sum="{summary}">\n'
            f'<h2><span class="num">01</span>A title</h2>\n{body}\n</section>\n')


class ScanTests(unittest.TestCase):
    def test_reads_chapters_and_their_blocks(self) -> None:
        page = WP.scan(chapter("<p>one</p>\n<h3>head</h3>\n<ul class=\"kpi-row\"><li>x</li></ul>"))

        self.assertEqual(["s01"], [item.id for item in page.chapters])
        self.assertEqual(["chapter-title", "paragraph", "section-title", "kpi-row"],
                         [block.role for block in page.chapters[0].blocks])
        self.assertEqual([], WP.validate(page))

    def test_nested_elements_are_not_blocks(self) -> None:
        page = WP.scan(chapter('<div class="insight"><h3>inside</h3><p>also inside</p></div>'))

        self.assertEqual(["chapter-title", "insight"],
                         [block.role for block in page.chapters[0].blocks])

    def test_the_first_class_names_the_block(self) -> None:
        page = WP.scan(chapter('<p class="formula">x = y</p><p class="src-note">note</p>'))

        self.assertEqual(["chapter-title", "formula", "source-note"],
                         [block.role for block in page.chapters[0].blocks])

    def test_a_figure_placeholder_is_a_block(self) -> None:
        page = WP.scan(chapter("<p>x</p>\n<!--FOLIO:FIGURE:release-gate-->"))

        figures = [block for block in page.blocks() if block.role == "figure"]
        self.assertEqual(1, len(figures))
        self.assertEqual("release-gate", figures[0].figure)

    def test_the_heading_and_summary_come_from_the_source(self) -> None:
        page = WP.scan(chapter("<p>x</p>", summary="what it argues"))

        self.assertEqual("01", page.chapters[0].number)
        self.assertEqual("A title", page.chapters[0].title)
        self.assertEqual("what it argues", page.chapters[0].summary)

    def test_the_real_fixtures_validate(self) -> None:
        for name in ("attention.frag.html", "reading.frag.html"):
            with self.subTest(fixture=name):
                page = WP.scan((FIXTURE / ("attention" if name.startswith("attention")
                                           else "reading-demo") / name).read_text(encoding="utf-8"))
                self.assertEqual([], WP.validate(page))
                self.assertGreaterEqual(len(page.chapters), 4)


class ValidateTests(unittest.TestCase):
    def test_an_unknown_block_fails(self) -> None:
        # A component the engine does not know is a contract change, not a
        # rendering detail: it must stop the build rather than fall through.
        page = WP.scan(chapter('<div class="new-thing">?</div>'))

        problems = WP.validate(page)
        self.assertTrue(any("new-thing" in problem for problem in problems), problems)

    def test_an_unwrapped_table_fails(self) -> None:
        page = WP.scan(chapter('<table class="tbl"><tr><td>x</td></tr></table>'))

        self.assertTrue(any("tbl-wrap" in problem for problem in WP.validate(page)))

    def test_a_chapter_without_a_heading_fails(self) -> None:
        page = WP.scan('<section class="chapter" id="s01"><p>orphan</p></section>')

        self.assertTrue(any("no h2" in problem for problem in WP.validate(page)))

    def test_a_chapter_without_an_id_fails(self) -> None:
        page = WP.scan('<section class="chapter"><h2>x</h2></section>')

        self.assertTrue(any("no id" in problem for problem in WP.validate(page)))

    def test_a_second_caption_after_a_figure_fails(self) -> None:
        # The figure owns its caption; a source-note under the plate describes
        # the same drawing a second time, in a second voice and often under a
        # second numbering.
        page = WP.scan(chapter('<!--FOLIO:FIGURE:release-gate-->\n'
                               '<p class="src-note">Figure 1: the gate.</p>'))

        self.assertTrue(any("repeats its caption" in problem for problem in WP.validate(page)))

    def test_a_source_note_elsewhere_is_a_note(self) -> None:
        page = WP.scan(chapter('<p class="src-note">Equal contribution.</p>\n'
                               '<!--FOLIO:FIGURE:release-gate-->'))

        self.assertEqual([], WP.validate(page))

    def test_a_fragment_without_chapters_fails(self) -> None:
        self.assertTrue(WP.validate(WP.scan("<p>loose</p>")))


class AnnotateTests(unittest.TestCase):
    def test_annotation_adds_the_role_and_a_unique_id(self) -> None:
        source = chapter("<p>one</p><p>two</p>")
        page = WP.scan(source)
        annotated = WP.annotate(source, page)

        self.assertEqual(2, annotated.count('data-folio-role="paragraph"'))
        ids = [block.id for block in page.blocks()]
        self.assertEqual(len(ids), len(set(ids)))
        for block_id in ids:
            self.assertIn(f'data-folio-id="{block_id}"', annotated)

    def test_annotation_changes_no_text(self) -> None:
        source = FRAGMENT.read_text(encoding="utf-8")
        annotated = WP.annotate(source, WP.scan(source))

        def text(value: str) -> str:
            import re
            return re.sub(r'<[^>]*>', '', value)

        self.assertEqual(text(source), text(annotated))

    def test_annotation_never_touches_a_figure_placeholder(self) -> None:
        source = chapter("<!--FOLIO:FIGURE:sign-off-->")
        annotated = WP.annotate(source, WP.scan(source))

        self.assertIn("<!--FOLIO:FIGURE:sign-off-->", annotated)

    def test_the_dom_agrees_with_the_model(self) -> None:
        # The promise W-STR-06 makes: parse what was written, count the roles,
        # compare with the model. This is the check without a browser.
        import re

        import check_web

        source = FRAGMENT.read_text(encoding="utf-8")
        page = WP.scan(source)
        annotated = WP.annotate(source, page)
        # The builder expands a placeholder into a figure block. Stand in for
        # it: the model saw the comment, the page holds the element.
        figure_ids = {block.figure: block.id for block in page.blocks() if block.figure}
        annotated = re.sub(
            r"<!--FOLIO:FIGURE:([a-z0-9-]+)-->",
            lambda match: (f'<figure class="figure" data-folio-role="figure" '
                           f'data-folio-id="{figure_ids[match.group(1)]}"></figure>'),
            annotated)

        root = check_web.Tree()
        root.feed(annotated)
        counted: dict[str, int] = {}
        for node in root.root.walk():
            role = node.attrs.get("data-folio-role")
            if role:
                counted[role] = counted.get(role, 0) + 1
        self.assertEqual(page.counts(), counted)


class ModeTests(unittest.TestCase):
    def test_off_leaves_the_source_alone(self) -> None:
        source = FRAGMENT.read_text(encoding="utf-8")
        rendered, page = WP.model_fragment(source, mode_name="off")

        self.assertEqual(source, rendered)
        self.assertEqual((), page.chapters)

    def test_shadow_reads_without_annotating(self) -> None:
        source = FRAGMENT.read_text(encoding="utf-8")
        rendered, page = WP.model_fragment(source, mode_name="shadow")

        self.assertEqual(source, rendered)
        self.assertTrue(page.chapters)

    def test_on_annotates(self) -> None:
        source = FRAGMENT.read_text(encoding="utf-8")
        rendered, _page = WP.model_fragment(source, mode_name="on")

        self.assertIn('data-folio-role="chapter-title"', rendered)

    def test_a_broken_page_stops_the_build_in_every_mode(self) -> None:
        broken = chapter('<div class="new-thing">?</div>')
        for name in ("shadow", "on"):
            with self.subTest(mode=name):
                with self.assertRaises(SystemExit):
                    WP.model_fragment(broken, mode_name=name)


if __name__ == "__main__":
    unittest.main()
