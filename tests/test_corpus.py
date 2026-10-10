"""Fixtures are reproducible inputs; the corpus guards script coverage.

Three defects found while authoring the first fixtures, each now pinned here:

  1. Placeholder keys kept their YAML quotes, so every lookup missed and
     templates rendered with the example text still in place.
  2. A quoted date such as 2026.10 was coerced to the float 2026.1, silently
     dropping the trailing zero.
  3. A placeholder key containing a colon was split at the wrong colon, so
     keys like "Fix 1: one-line description." never matched.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus


class PlaceholderFillTests(TestCase):
    def test_bare_and_wrapped_keys_are_both_accepted(self) -> None:
        template = "<p>{{TITLE}}</p><p>{{BODY}}</p>"
        rendered, filled, remaining = corpus.fill_template(
            template, {"TITLE": "hello", "{{BODY}}": "world"}
        )
        self.assertIn("hello", rendered)
        self.assertIn("world", rendered)
        self.assertEqual(2, filled)
        self.assertEqual([], remaining)

    def test_unfilled_placeholders_are_reported(self) -> None:
        rendered, filled, remaining = corpus.fill_template("<p>{{A}}{{B}}</p>", {"A": "x"})
        self.assertEqual(1, filled)
        self.assertEqual(["B"], remaining)
        self.assertIn("{{B}}", rendered)

    def test_a_value_may_contain_markup(self) -> None:
        rendered, _, _ = corpus.fill_template(
            "<p>{{X}}</p>", {"X": '<span class="hl">42</span>'}
        )
        self.assertIn('<span class="hl">42</span>', rendered)

    def test_placeholders_are_not_clobbered_by_substituted_text(self) -> None:
        # A value that itself looks like a placeholder must not be re-expanded.
        rendered, _, remaining = corpus.fill_template("<p>{{A}}</p>", {"A": "{{B}}"})
        self.assertIn("{{B}}", rendered)
        self.assertIn("B", remaining)


class YamlSubsetTests(TestCase):
    def test_quoted_key_loses_its_quotes(self) -> None:
        data = corpus._parse_yaml('content:\n  "{{TITLE}}": "hello"\n')
        self.assertEqual({"{{TITLE}}": "hello"}, data["content"])

    def test_quoted_numeric_value_keeps_trailing_zero(self) -> None:
        # 2026.10 as a float is 2026.1; a version must survive as written.
        data = corpus._parse_yaml('content:\n  "{{DATE}}": "2026.10"\n')
        self.assertEqual("2026.10", data["content"]["{{DATE}}"])

    def test_content_values_stay_text_even_unquoted(self) -> None:
        data = corpus._parse_yaml("content:\n  DATE: 2026.10\n")
        self.assertEqual("2026.10", data["content"]["DATE"])

    def test_key_containing_a_colon_survives(self) -> None:
        data = corpus._parse_yaml('content:\n  "Fix 1: one-line description.": "done"\n')
        self.assertEqual({"Fix 1: one-line description.": "done"}, data["content"])

    def test_quoted_key_containing_a_colon_and_quotes_survives(self) -> None:
        raw = 'content:\n  "Thank contributors, e.g. \\"Thanks\\".": "cheers"\n'
        data = corpus._parse_yaml(raw)
        self.assertEqual(1, len(data["content"]))

    def test_block_scalar_is_read_as_one_value(self) -> None:
        data = corpus._parse_yaml("content:\n  BODY: |\n    first line\n    second line\n")
        self.assertIn("first line", data["content"]["BODY"])
        self.assertIn("second line", data["content"]["BODY"])

    def test_non_content_values_keep_their_types(self) -> None:
        data = corpus._parse_yaml("expected:\n  hard:\n    pages: 2\n")
        self.assertEqual(2, data["expected"]["hard"]["pages"])

    def test_lists_are_parsed(self) -> None:
        data = corpus._parse_yaml("purpose:\n  - cjk\n  - pagination\n")
        self.assertEqual(["cjk", "pagination"], data["purpose"])

    def test_booleans_are_parsed_outside_content(self) -> None:
        data = corpus._parse_yaml("adversarial: true\n")
        self.assertTrue(data["adversarial"])

    def test_flow_mapping_is_parsed(self) -> None:
        data = corpus._parse_yaml("expected:\n  hard: {pages: 1, overflow: 0}\n")
        self.assertEqual({"pages": 1, "overflow": 0}, data["expected"]["hard"])


class ShippedFixtureTests(TestCase):
    def test_fixtures_are_discovered(self) -> None:
        paths = corpus.discover_fixtures()
        self.assertGreaterEqual(len(paths), 8)

    def test_every_fixture_is_valid(self) -> None:
        for path in corpus.discover_fixtures():
            with self.subTest(fixture=path.stem):
                problems = corpus.validate_fixture(corpus.load_fixture(path), path)
                self.assertEqual([], problems)

    def test_every_fixture_id_matches_its_filename(self) -> None:
        for path in corpus.discover_fixtures():
            with self.subTest(fixture=path.stem):
                self.assertEqual(path.stem, corpus.load_fixture(path)["id"])

    def test_all_four_script_profiles_are_covered(self) -> None:
        # The corpus exists to exercise CJK, Latin, digits and their mixture. A
        # corpus that drifts to one writing system stops doing that.
        profiles = {corpus.load_fixture(p)["script_profile"] for p in corpus.discover_fixtures()}
        # RTL values were added with the coverage matrix: a fixture that
        # exercises Arabic shaping cannot declare itself as a left-to-right
        # composition.
        self.assertEqual(
            {"han-only", "latin-only", "digits-heavy", "han-latin-digits",
             "rtl-only", "rtl-with-latin"},
            profiles,
        )

    def test_mixed_script_fixtures_carry_both_writing_systems(self) -> None:
        for path in corpus.discover_fixtures():
            data = corpus.load_fixture(path)
            if data["script_profile"] != "han-latin-digits":
                continue
            with self.subTest(fixture=path.stem):
                blob = json.dumps(data["content"], ensure_ascii=False)
                has_han = any("\u4e00" <= ch <= "\u9fff" for ch in blob)
                has_latin = any("a" <= ch.lower() <= "z" for ch in blob)
                has_digits = any(ch.isdigit() for ch in blob)
                self.assertTrue(has_han, "mixed fixture should contain Han characters")
                self.assertTrue(has_latin, "mixed fixture should contain Latin letters")
                self.assertTrue(has_digits, "mixed fixture should contain digits")

    def test_adversarial_share_meets_the_target(self) -> None:
        paths = corpus.discover_fixtures()
        adversarial = sum(1 for p in paths if corpus.load_fixture(p).get("adversarial"))
        # The blueprints call for at least 20% boundary content; a corpus made
        # only of happy paths cannot find where rendering breaks.
        self.assertGreaterEqual(adversarial / len(paths), 0.20)

    def test_every_fixture_declares_provenance(self) -> None:
        for path in corpus.discover_fixtures():
            with self.subTest(fixture=path.stem):
                provenance = corpus.load_fixture(path)["provenance"]
                self.assertIn("license", provenance)
                self.assertIn("type", provenance)

    def test_fixture_ids_are_unique(self) -> None:
        ids = [corpus.load_fixture(p)["id"] for p in corpus.discover_fixtures()]
        self.assertEqual(len(ids), len(set(ids)))


class TemplateResolutionTests(TestCase):
    def test_language_selects_the_matching_template(self) -> None:
        zh = corpus._template_for({"genre": "one-pager", "language": "zh-Hans-CN"})
        en = corpus._template_for({"genre": "one-pager", "language": "en-US"})
        self.assertEqual("one-pager.html", zh.name)
        self.assertEqual("one-pager-en.html", en.name)

    def test_explicit_template_overrides_the_default(self) -> None:
        chosen = corpus._template_for(
            {"genre": "changelog", "language": "en-US", "template": "changelog.html"}
        )
        self.assertEqual("changelog.html", chosen.name)

    def test_every_fixture_template_exists(self) -> None:
        for path in corpus.discover_fixtures():
            data = corpus.load_fixture(path)
            with self.subTest(fixture=path.stem):
                self.assertTrue(corpus._template_for(data).is_file())


class CorpusRenderTests(TestCase):
    """Rendering a fixture must be reproducible and must honour its contract."""

    def test_a_fixture_renders_and_reports_pages(self) -> None:
        import tempfile

        path = ROOT / "references" / "fixtures" / "document" / "minimal" / "minimal-zh-changelog.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            result = corpus.render_fixture(path, Path(tmp))
        self.assertTrue(result.ok, result.problems)
        self.assertIsNotNone(result.pages)
        self.assertGreater(result.pages, 0)

    def test_rendering_is_reproducible(self) -> None:
        import tempfile

        path = ROOT / "references" / "fixtures" / "document" / "minimal" / "minimal-mixed-changelog.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            first = corpus.render_fixture(path, Path(tmp) / "a")
            second = corpus.render_fixture(path, Path(tmp) / "b")
        self.assertEqual(first.pages, second.pages)

    def test_every_fixture_renders_within_its_contract(self) -> None:
        # Full corpus rendering runs in CI; this samples one per script profile
        # so the suite stays quick while still covering each writing system.
        import tempfile

        sample = [
            "minimal/minimal-zh-changelog.yaml",
            "minimal/minimal-en-changelog.yaml",
            "minimal/minimal-digits-changelog.yaml",
            "minimal/minimal-mixed-changelog.yaml",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for rel in sample:
                with self.subTest(fixture=rel):
                    result = corpus.render_fixture(
                        ROOT / "references" / "fixtures" / "document" / rel, Path(tmp)
                    )
                    self.assertTrue(result.ok, result.problems)

    def test_page_expectation_is_checked(self) -> None:
        import tempfile

        path = ROOT / "references" / "fixtures" / "document" / "minimal" / "minimal-zh-changelog.yaml"
        data = corpus.load_fixture(path)
        data["expected"]["hard"] = {"pages": 99}
        broken = Path(tmp_dir := tempfile.mkdtemp()) / "minimal-zh-changelog.yaml"
        # Write a fixture with an impossible contract and confirm it is caught.
        import json as _json

        broken.write_text(
            path.read_text(encoding="utf-8").replace("pages_max: 2", "pages_max: 99")
            .replace("pages_min: 1", "pages_min: 98"),
            encoding="utf-8",
        )
        result = corpus.render_fixture(broken, Path(tmp_dir) / "out")
        self.assertFalse(result.ok)
        self.assertTrue(any("pages" in p for p in result.problems), result.problems)
        _json.dumps(result.to_dict())

    def test_results_serialise_for_a_build_artifact(self) -> None:
        import json as _json
        import tempfile

        path = ROOT / "references" / "fixtures" / "document" / "minimal" / "minimal-en-changelog.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            result = corpus.render_fixture(path, Path(tmp))
        payload = result.to_dict()
        _json.dumps(payload)
        self.assertIn("placeholders", payload)
        self.assertIn("script_profile", payload)
