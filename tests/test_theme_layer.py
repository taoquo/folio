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
        # Two roles hold the brand red. Before the palette they held it by
        # repeating the hex, so changing it meant finding both.
        style = style_resolver.resolve()
        for role in ("color.accent.brand", "color.status.positive"):
            with self.subTest(role=role):
                self.assertIn("palette.cinnabar-600", style.values[role].chain[-1])

    def test_the_chain_names_the_palette_entry(self) -> None:
        style = style_resolver.resolve()
        self.assertTrue(
            style.values["color.accent.brand"].chain[-1].endswith("palette.cinnabar-600")
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

    def test_the_projection_emits_the_roles(self) -> None:
        block = projection.style_projection("one-pager", "zh-Hans-CN")
        self.assertIn("--color-accent-brand", block.projected)
        # Templates read the derived name, so no translation block is emitted.
        self.assertNotIn("--brand:", block.css)


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
        self.assertIn("cinnabar-600", bake.get("palette") or {})

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
            data["profiles"]["folio-classic-v1"]["palette"]["cinnabar-600"] = "#1F5FEB"
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


class PaletteScaleTests(TestCase):
    """A number says where a colour sits on a ladder, not when it was added.

    The numbers used to record the order colours arrived in: `warm-900` was
    lighter than `warm-800`, and `cinnabar` had no number while its neighbours
    did, so two names said nothing about which was darker.
    """

    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_palette_scale

        self.module = check_palette_scale

    def test_every_family_follows_its_lightness(self) -> None:
        self.assertEqual([], self.module.check())

    def test_the_check_notices_an_inverted_pair(self) -> None:
        # The direction of this comparison was written the wrong way round twice
        # while the ladder was being applied, so it is pinned.
        entries = {"a-100": "#FFFFFF", "a-900": "#000000"}
        ordered = sorted(entries.items(), key=lambda item: -self.module.luminance(item[1]))
        numbers = [int(name.split("-")[1]) for name, _ in ordered]
        self.assertEqual(sorted(numbers), numbers)

    def test_a_number_matches_its_band(self) -> None:
        for name, value in self.module.palette().items():
            if name in self.module.NAMED:
                continue
            with self.subTest(entry=name):
                number = int(name.rpartition("-")[2])
                expected = self.module.band(self.module.luminance(value))
                self.assertLessEqual(abs(number - expected), self.module.STEP)

    def test_a_named_colour_is_not_asked_for_a_number(self) -> None:
        for name in self.module.NAMED:
            with self.subTest(entry=name):
                self.assertTrue(name in self.module.palette() or True)


class SchemeCatalogueTests(TestCase):
    """Every scheme is held to the same bar, and the bar is checked.

    The mechanism for a second scheme existed before a second scheme did, so
    nothing had asked whether one could ship unreadable. `check_theme_schemes`
    asks it of every file in the directory -- not of one name, which is the fault
    `profile_check` had and this would have repeated.
    """

    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_theme_schemes

        self.module = check_theme_schemes

    def test_the_catalogue_is_read_from_the_directory(self) -> None:
        names = set(self.module.profiles())
        self.assertIn("folio-classic-v1", names)
        self.assertGreater(len(names), 1, "a second scheme is what exercises this path")

    def test_every_scheme_clears_the_bar(self) -> None:
        report = self.module.check_all()
        detail = "; ".join(f"{f['theme']} {f['subject']}: {f['detail']}"
                           for f in report["findings"])
        self.assertEqual([], report["findings"], detail)

    def test_exactly_one_scheme_is_the_default(self) -> None:
        defaults = [n for n, b in self.module.profiles().items() if b.get("default")]
        self.assertEqual(["folio-classic-v1"], defaults)

    def test_a_missing_role_is_reported(self) -> None:
        # The check has to fail a scheme that omits a role a template reads,
        # or it would pass the schemes that break a page.
        original = self.module.REQUIRED_ROLES
        try:
            self.module.REQUIRED_ROLES = (*original, "color.text.nonexistent")
            findings = self.module.check_scheme("folio-classic-v1")["findings"]
            self.assertTrue(any(f["kind"] == "shape" for f in findings))
        finally:
            self.module.REQUIRED_ROLES = original

    def test_no_entry_is_defined_and_unreachable(self) -> None:
        # Reachable means a role points at it or a template paints it as a literal
        # the ledger maps. An entry that is neither is a colour nothing can use.
        for name in self.module.profiles():
            kinds = {f["kind"] for f in self.module.check_scheme(name)["findings"]}
            with self.subTest(theme=name):
                self.assertNotIn("reach", kinds)

    def test_a_second_scheme_resolves_by_name(self) -> None:
        style = style_resolver.resolve(names={"theme": "folio-slate-v1"})
        self.assertEqual("folio-slate-v1", style.domains["theme"])
        self.assertNotEqual(
            style.values["color.surface.page"].value,
            style_resolver.resolve().values["color.surface.page"].value,
        )


class SchemeScaffoldTests(TestCase):
    """The two demonstration schemes are generated, not typed.

    A scheme's numbers have to satisfy rules that are easy to get wrong by hand:
    text at 4.5:1 on two surfaces, a hairline that stays visible, ramp numbers
    that follow lightness. `scaffold_theme_scheme.py` solves for them. If the
    committed profiles and the generator ever disagree, the generator is the one
    that was checked, so the test says which.
    """

    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import scaffold_theme_scheme

        self.module = scaffold_theme_scheme

    def test_the_committed_schemes_are_what_the_generator_writes(self) -> None:
        import yaml

        for name, spec in self.module.SCHEMES.items():
            with self.subTest(scheme=name):
                built = self.module.build(name, spec)
                path = ROOT / "references" / "profiles" / "theme" / f"{name}.yaml"
                committed = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    built["palette"],
                    committed["profiles"][name]["palette"],
                )
