"""The colour layer: one palette, roles that point at it, and a way to select a scheme.

These tests cover what the architecture change is for. Each one fails if the
layer stops being a single source: a role that holds its own hex, a variable
whose name is hand-written, or a theme that cannot be selected.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import projection  # noqa: E402
import style_resolver  # noqa: E402


class PaletteLayerTests(TestCase):
    def test_a_role_resolves_through_the_palette(self) -> None:
        style = style_resolver.resolve()
        self.assertEqual(
            style.values["palette.ink"].value,
            style.values["color.text.primary"].value,
        )

    def test_the_roles_sharing_the_brand_share_one_palette_entry(self) -> None:
        # Five roles hold the brand red. Before the palette they held it by
        # repeating the hex, so changing it meant finding all five.
        style = style_resolver.resolve()
        for role in ("color.accent.brand", "color.status.positive",
                     "color.data.category-1", "color.data.diverging-positive"):
            with self.subTest(role=role):
                self.assertIn("palette.cinnabar", style.values[role].chain[-1])

    def test_the_chain_names_the_palette_entry(self) -> None:
        style = style_resolver.resolve()
        self.assertTrue(
            style.values["color.accent.brand"].chain[-1].endswith("palette.cinnabar")
        )

    def test_no_role_holds_a_reference_instead_of_a_colour(self) -> None:
        style = style_resolver.resolve()
        for path, value in style.values.items():
            if path.startswith("color."):
                with self.subTest(role=path):
                    self.assertTrue(str(value.value).startswith("#"))


class DerivedNameTests(TestCase):
    def test_a_colour_variable_is_derived_from_its_path(self) -> None:
        # One rule, so a new role needs one name rather than two.
        self.assertEqual("--color-text-primary", projection.colour_variable("color.text.primary"))
        self.assertEqual("--color-data-category-1",
                         projection.colour_variable("color.data.category-1"))

    def test_every_projected_colour_uses_the_derived_name(self) -> None:
        style = style_resolver.resolve()
        for path, variable, value in projection.colour_paths(style):
            with self.subTest(path=path):
                self.assertEqual(projection.colour_variable(path), variable)
                self.assertTrue(value.startswith("#"))

    def test_the_projection_emits_the_roles_and_their_aliases(self) -> None:
        block = projection.style_projection("one-pager", "zh-Hans-CN")
        self.assertIn("--color-accent-brand", block.projected)
        self.assertIn("--brand: var(--color-accent-brand)", block.css)


class ThemeSelectionTests(TestCase):
    def test_the_default_theme_is_the_one_marked_default(self) -> None:
        self.assertEqual("folio-classic-v1", style_resolver.default_theme_name())

    def test_a_named_theme_is_used(self) -> None:
        style = style_resolver.resolve(names={"theme": "folio-classic-v1"})
        self.assertEqual("folio-classic-v1", style.domains["theme"])

    def test_an_unknown_theme_is_reported_with_what_exists(self) -> None:
        style = style_resolver.resolve(names={"theme": "no-such-theme"})
        violations = " ".join(style.violations)
        self.assertIn("no-such-theme", violations)
        self.assertIn("folio-classic-v1", violations)

    def test_the_projection_takes_a_theme(self) -> None:
        block = projection.style_projection("one-pager", "zh-Hans-CN", "folio-classic-v1")
        self.assertIn("--color-accent-brand", block.projected)


class ConsumptionTests(TestCase):
    def test_no_projected_variable_is_silently_unread(self) -> None:
        # The failure this repository keeps repeating: a value resolved and
        # consumed by nobody. Known debt is listed with a reason; anything else
        # is a mistake.
        self.assertEqual([], projection.unconsumed_variables())

    def test_the_acknowledged_debt_names_a_reason(self) -> None:
        for name, reason in projection.UNCONSUMED.items():
            with self.subTest(variable=name):
                self.assertTrue(reason.strip())


class StaticBakeTests(TestCase):
    """The pages a reader opens directly carry the palette, written in.

    `index.html`, `index-zh.html` and `assets/demos/*.html` have no build step at
    view time, so their colours are baked. A marker names the theme and a sidecar
    records the values, because replacing by value is one-way without one: once a
    new hex is written the page no longer says which palette entry it stood for.
    """

    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_static_theme

        self.module = build_static_theme

    def test_the_pages_are_where_they_are_expected(self) -> None:
        names = {path.name for path in self.module.targets()}
        self.assertIn("index.html", names)
        self.assertIn("index-zh.html", names)
        self.assertIn("demo-tesla.html", names)

    def test_a_rendered_template_is_not_a_target(self) -> None:
        # Diagram templates are retargeted at render time; writing them here
        # would duplicate that and break the ledger check.
        relatives = {str(path.relative_to(ROOT)) for path in self.module.targets()}
        self.assertNotIn("assets/diagrams/bar-chart.html", relatives)

    def test_every_page_says_which_theme_it_holds(self) -> None:
        for path in self.module.targets():
            with self.subTest(page=path.name):
                text = path.read_text(encoding="utf-8", errors="ignore")
                self.assertIsNotNone(self.module.baked_theme(text))

    def test_the_sidecar_records_the_palette_that_was_written(self) -> None:
        bake = self.module.read_bake()
        self.assertEqual("folio-classic-v1", bake.get("theme"))
        self.assertIn("cinnabar", bake.get("palette") or {})

    def test_the_default_theme_needs_no_substitution(self) -> None:
        self.assertEqual({}, self.module.substitution_for(None))

    def test_a_changed_palette_produces_a_substitution(self) -> None:
        # The sidecar holds the values in the pages; a palette entry that moved
        # has to produce a mapping, or the pages would silently keep the old one.
        import yaml

        profile = ROOT / "references" / "profiles" / "theme" / "folio-classic-v1.yaml"
        original = profile.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(original)
            data["profiles"]["folio-classic-v1"]["palette"]["cinnabar"] = "#1F5FEB"
            profile.write_text(
                original[:original.index("version:")]
                + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100,
                                 default_flow_style=False),
                encoding="utf-8",
            )
            mapping = self.module.substitution_for(None)
            self.assertEqual("#1F5FEB", mapping.get("#B83D2E"))
        finally:
            profile.write_text(original, encoding="utf-8")

    def test_checking_is_read_only(self) -> None:
        before = {p: p.read_bytes() for p in self.module.targets()}
        self.module.apply(None, check=True)
        for path, content in before.items():
            with self.subTest(page=path.name):
                self.assertEqual(content, path.read_bytes())
