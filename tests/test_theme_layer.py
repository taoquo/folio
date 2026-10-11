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
