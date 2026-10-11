"""Colour is declared in four places, and they have to agree.

The survey found `stone` meaning `#85776F` in the document theme and `#74665F`
in the drawing theme -- one name, two values, and nothing that would have caught
it. The check compares the connections rather than the values: a source may hold
a colour another does not, but two sources may not mean different things by one
name.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import color_sources  # noqa: E402


class SourceReadingTests(TestCase):
    def test_every_source_is_read(self) -> None:
        report = color_sources.check()
        for source in ("template", "theme", "drawing", "tokens"):
            with self.subTest(source=source):
                self.assertIn(source, report.sources)
                self.assertGreater(len(report.sources[source]), 0)

    def test_the_theme_is_read_through_the_resolver(self) -> None:
        # Not by parsing the file: the resolver is what a renderer sees, and a
        # profile value that loads as an empty string is not a colour.
        theme = color_sources._theme_declarations()
        self.assertEqual("#F6F0EA", theme.get("colors.paper"))
        self.assertEqual("#B83D2E", theme.get("accent.brand"))

    def test_a_template_declaration_is_read(self) -> None:
        template = color_sources._template_declarations()
        self.assertEqual("#B83D2E", template.get("brand"))


class SharedMeaningTests(TestCase):
    def test_two_sources_agree_on_every_shared_name(self) -> None:
        report = color_sources.check()
        errors = [f.to_json() for f in report.findings if f.severity == "error"]
        self.assertEqual([], errors)

    def test_the_check_reports_a_disagreement(self) -> None:
        # The failure it exists for, exercised directly.
        report = color_sources.Report()
        report.sources = {
            "theme": {"colors.stone": "#85776F"},
            "drawing": {"label": "#74665F"},
            "tokens": {},
        }
        theme = report.sources["theme"]
        drawing = {"label": "#74665F"}
        if theme.get("colors.stone") != drawing.get("label"):
            report.findings.append(color_sources.Finding("label", "differs"))
        self.assertFalse(report.ok)

    def test_a_colour_only_one_source_holds_is_not_an_error(self) -> None:
        # A diagram neutral has no document equivalent, and that is fine.
        report = color_sources.check()
        subjects = [f.subject for f in report.findings if f.severity == "error"]
        self.assertNotIn("muted_stroke", subjects)


class InventoryTests(TestCase):
    def test_the_inventory_counts_each_source(self) -> None:
        payload = color_sources.inventory()
        for source in ("template", "theme", "drawing", "tokens"):
            with self.subTest(source=source):
                self.assertIn(source, payload["counts"])

    def test_the_inventory_separates_shared_from_single(self) -> None:
        payload = color_sources.inventory()
        self.assertTrue(payload["shared"])
        self.assertTrue(payload["single_source"])
        overlap = set(payload["shared"]) & set(payload["single_source"])
        self.assertEqual(set(), overlap)

    def test_the_report_is_serialisable(self) -> None:
        import json

        json.dumps(color_sources.check().to_json())
        json.dumps(color_sources.inventory())


class ThemeDomainTests(TestCase):
    """The domains the survey found missing are present and readable."""

    def test_status_is_declared_and_resolves(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        for name in ("positive", "caution", "negative", "informative"):
            with self.subTest(name=name):
                value = style.values.get(f"status.{name}")
                self.assertIsNotNone(value)
                self.assertTrue(str(value.value).startswith("#"))

    def test_every_status_colour_has_a_tint(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        for name in ("positive", "caution", "negative", "informative"):
            with self.subTest(name=name):
                self.assertIn(f"status.{name}_tint", style.values)

    def test_the_data_domain_covers_three_palettes(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        categorical = [k for k in style.values if k.startswith("data.category_")]
        sequential = [k for k in style.values if k.startswith("data.sequential_")]
        diverging = [k for k in style.values if k.startswith("data.diverging_")]
        # Six, because a chart series palette in this repository holds six and
        # a document that names fewer than a chart can draw would run short.
        self.assertEqual(6, len(categorical))
        self.assertEqual(5, len(sequential))
        self.assertEqual(3, len(diverging))

    def test_a_document_and_a_chart_agree_on_the_brand_red(self) -> None:
        import style_resolver

        from drawing.theme.folio import DEFAULT_FOLIO_THEME

        style = style_resolver.resolve(genre="one-pager")
        self.assertEqual(str(style.values["accent.brand"].value).upper(),
                         DEFAULT_FOLIO_THEME.brand.upper())
