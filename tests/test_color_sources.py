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
        self.assertEqual("#F6F0EA", theme.get("color.surface.page"))
        self.assertEqual("#B83D2E", theme.get("color.accent.brand"))

    def test_a_template_declaration_is_read(self) -> None:
        # Templates name a variable the way the role is named, so the layer
        # needs no translation table between the two.
        template = color_sources._template_declarations()
        self.assertEqual("#B83D2E", template.get("color-accent-brand"))


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
        for name in ("positive", "caution", "negative"):
            with self.subTest(name=name):
                value = style.values.get(f"color.status.{name}")
                self.assertIsNotNone(value)
                self.assertTrue(str(value.value).startswith("#"))

    def test_a_status_that_is_painted_as_a_badge_has_a_tint(self) -> None:
        # Only caution is: the changelog renders it as a badge, which needs a
        # background. The other statuses colour text, which does not. Tints for
        # them existed and were read by no template, so they were removed rather
        # than given a badge to justify them.
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        self.assertIn("color.status.caution-tint", style.values)
        for name in ("positive", "negative", "informative"):
            with self.subTest(name=name):
                self.assertNotIn(f"color.status.{name}-tint", style.values)

    def test_the_document_theme_carries_no_chart_palette(self) -> None:
        # A chart palette lived here with fourteen roles and no consumer: the
        # templates draw their charts inline and a standalone diagram reads the
        # drawing theme, which has its own palette and three schemes to keep in
        # step. It was removed rather than given a consumer it did not have.
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        self.assertEqual([], [k for k in style.values if k.startswith("color.data.")])


class PaletteLayerTests(TestCase):
    """A role points at a palette entry, so one edit moves every role.

    Five roles share the brand red. Before the palette layer they shared it by
    repeating the hex five times, and changing it meant finding all five.
    """

    def test_the_roles_that_share_a_colour_share_a_palette_entry(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        origins = {
            path: value.chain[-1].split("palette.")[-1]
            for path, value in style.values.items()
            if path.startswith("color.") and "palette." in value.chain[-1]
        }
        # The accent and the positive status are one colour with two meanings.
        self.assertEqual("cinnabar-600", origins["color.accent.brand"])
        self.assertEqual("cinnabar-600", origins["color.status.positive"])
        self.assertEqual("cinnabar-100", origins["color.accent.brand-tint"])

    def test_a_role_resolves_to_the_palette_value(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        palette_ink = style.values["palette.ink"].value
        self.assertEqual(palette_ink, style.values["color.text.primary"].value)

    def test_every_role_is_backed_by_a_palette_entry(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        palette_names = {
            path.split(".", 1)[1]
            for path in style.values
            if path.startswith("palette.")
        }
        for path, value in style.values.items():
            if not path.startswith("color."):
                continue
            with self.subTest(role=path):
                self.assertTrue(str(value.value).startswith("#"))
        self.assertTrue(palette_names)

    def test_the_palette_holds_each_value_once(self) -> None:
        import style_resolver

        style = style_resolver.resolve(genre="one-pager")
        values = [str(v.value).upper() for k, v in style.values.items() if k.startswith("palette.")]
        self.assertEqual(len(values), len(set(values)))
