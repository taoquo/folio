"""The compatibility writer fills the template's own markup.

The writer first rebuilt a document's markup from the IR and matched on pages
and fonts while rendering a single stacked column where the template laid out
two. A template's appearance is its DOM shape: `.header .title-block .eyebrow`
only matches when all three levels are present. These tests hold the writer to
filling that shape rather than reproducing it.
"""

import re
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from document_ir.bridge import bridge_template, default_map_for
from document_ir.writers.skeleton import attach_ids, collect_values, fill_template

FIXTURES = ROOT / "references" / "fixtures" / "document"
TEMPLATES = ROOT / "assets" / "templates"


def _document(genre: str, fixture: Path):
    import corpus
    from shadow import _template_for

    data = corpus.load_fixture(fixture)
    template_path = _template_for(data)
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        (k[2:-2] if k.startswith("{{") and k.endswith("}}") else k): v
        for k, v in (data.get("content") or {}).items()
    }
    document = bridge_template(
        template_text, values,
        document_id=data.get("id", fixture.stem),
        lang=data.get("language", "en-US"),
        genre=genre,
        bridge_map=default_map_for(genre, data.get("language", "en-US")),
    )
    return template_text, document, data


class SkeletonTests(TestCase):
    def _one_pager(self):
        fixture = FIXTURES / "canonical" / "canonical-zh-one-pager.yaml"
        if not fixture.is_file():
            self.skipTest("fixture not present")
        return _document("one-pager", fixture)

    def test_the_template_markup_is_reused_not_rebuilt(self) -> None:
        template_text, document, _ = self._one_pager()
        result = fill_template(template_text, document)
        # The containers the template lays out with must survive, because the
        # stylesheet reaches them through descendant selectors.
        for css in ("header", "title-block", "metrics", "decision-strip", "two-col", "footer"):
            with self.subTest(container=css):
                self.assertIn(f'class="{css}"', result.html)

    def test_every_declared_placeholder_is_filled(self) -> None:
        template_text, document, _ = self._one_pager()
        result = fill_template(template_text, document)
        self.assertEqual([], result.missing)

    def test_no_placeholder_survives_in_a_filled_document(self) -> None:
        template_text, document, _ = self._one_pager()
        html = fill_template(template_text, document).html
        # A leftover placeholder is visible to a reader of the file and also
        # means a slot silently rendered nothing.
        leftover = [m.group(1) for m in re.finditer(r"\{\{([^{}]*)\}\}", html)]
        self.assertEqual([], leftover[:5])

    def test_the_head_is_filled_too(self) -> None:
        template_text, document, _ = self._one_pager()
        html = fill_template(template_text, document).html
        head = html.split("</head>")[0]
        self.assertNotIn("{{", head)

    def test_inline_emphasis_survives(self) -> None:
        template_text, document, _ = self._one_pager()
        html = fill_template(template_text, document).html
        # The fixture marks a phrase with <strong>; flattening it to plain text
        # would drop a decision the author made.
        self.assertIn("<strong>", html)

    def test_a_list_renders_its_items(self) -> None:
        template_text, document, _ = self._one_pager()
        html = fill_template(template_text, document).html
        items = re.findall(r"<li>(.*?)</li>", html, re.DOTALL)
        self.assertTrue(items)
        for item in items:
            with self.subTest(item=item[:20]):
                self.assertTrue(item.strip(), "a bullet rendered with no text")

    def test_repeated_slots_get_distinct_values(self) -> None:
        template_text, document, _ = self._one_pager()
        html = fill_template(template_text, document).html
        items = [i.strip() for i in re.findall(r"<li>(.*?)</li>", html, re.DOTALL)]
        self.assertGreater(len(set(items)), 1, "every bullet took the same value")

    def test_values_are_collected_from_nested_inline_nodes(self) -> None:
        _, document, _ = self._one_pager()
        values = collect_values(document)
        joined = " ".join(values.values())
        self.assertIn("可测量的质量体系", joined)

    def test_ids_are_attached_for_provenance(self) -> None:
        template_text, document, _ = self._one_pager()
        html = attach_ids(fill_template(template_text, document).html, document)
        self.assertIn("data-folio-id=", html)
        ids = set(document.node_ids())
        found = set(re.findall(r'data-folio-id="([^"]+)"', html))
        self.assertTrue(found & ids, "no rendered id maps back to an IR node")


class FidelityHarnessTests(TestCase):
    def test_the_harness_finds_a_fixture_per_genre(self) -> None:
        import fidelity

        for genre in ("one-pager", "changelog", "resume"):
            with self.subTest(genre=genre):
                self.assertIsNotNone(fidelity._fixture_for(genre))

    def test_a_measured_result_reports_its_dimensions(self) -> None:
        import fidelity

        item = fidelity.Fidelity(genre="x", fixture="f", template="t")
        payload = item.to_json()
        for key in ("ssim", "changed_ratio", "complete", "acceptable"):
            self.assertIn(key, payload)

    def test_an_incomplete_result_is_not_acceptable(self) -> None:
        import fidelity

        item = fidelity.Fidelity(genre="x", fixture="f", template="t", ssim=1.0,
                                 changed_ratio=0.0, missing=["A"])
        self.assertFalse(item.acceptable)

    def test_a_complete_and_identical_result_is_acceptable(self) -> None:
        import fidelity

        item = fidelity.Fidelity(genre="x", fixture="f", template="t", ssim=1.0,
                                 changed_ratio=0.0, pages_match=True)
        self.assertTrue(item.acceptable)
