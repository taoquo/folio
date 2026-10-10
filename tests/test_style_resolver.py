"""Style resolution: deterministic values with a traceable origin.

The plan asks two questions of a resolved style: is it the same every time, and
can you say which profile decided a value. The first needs determinism, the
second needs an origin on every field. Both are checked here, along with the
domain separation the profile kinds claim to have.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import style_resolver  # noqa: E402


class ResolutionTests(TestCase):
    def test_every_domain_contributes_a_profile(self) -> None:
        style = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        for kind in ("typography", "page", "language", "theme", "taste"):
            with self.subTest(kind=kind):
                self.assertIn(kind, style.domains)

    def test_resolution_is_deterministic(self) -> None:
        first = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        second = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        self.assertEqual(first.to_json(), second.to_json())

    def test_every_value_names_its_source(self) -> None:
        style = style_resolver.resolve(genre="resume", language="en-US")
        for path, item in style.values.items():
            with self.subTest(path=path):
                self.assertTrue(item.source, f"{path} has no source")

    def test_a_declared_default_is_visible(self) -> None:
        # `paragraph.widows` is declared in the file's shared defaults rather
        # than in any single profile, and a resolver that cannot see it cannot
        # explain the page it produced.
        style = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        self.assertEqual(2, style.get("paragraph.widows"))
        self.assertIn("defaults", style.source_of("paragraph.widows"))

    def test_explanation_names_the_chain(self) -> None:
        style = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        text = style.explain("body.size_pt")
        self.assertIn("body.size_pt", text)
        self.assertIn("typography", text)

    def test_an_unknown_path_explains_nothing_rather_than_guessing(self) -> None:
        style = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        self.assertIn("not set", style.explain("no.such.field"))

    def test_an_unknown_profile_is_reported(self) -> None:
        style = style_resolver.resolve(names={"typography": "does-not-exist"})
        self.assertTrue(any("not found" in v for v in style.violations))

    def test_domains_stay_in_their_own_fields(self) -> None:
        # A typography profile that set a colour, or a theme that set a page
        # size, would mean the separation the profiles claim is not real.
        style = style_resolver.resolve(genre="one-pager", language="zh-Hans-CN")
        self.assertEqual([], style.violations)

    def test_field_ownership_is_declared_for_every_domain(self) -> None:
        for kind in ("typography", "page", "language", "theme", "taste"):
            with self.subTest(kind=kind):
                self.assertTrue(style_resolver.DOMAIN_FIELDS.get(kind))

    def test_a_foreign_field_is_refused(self) -> None:
        # Asked directly, the ownership rule rejects a colour under typography.
        self.assertFalse(style_resolver._owned_by("typography", "colors.ink"))
        self.assertTrue(style_resolver._owned_by("theme", "colors.ink"))
        self.assertFalse(style_resolver._owned_by("theme", "margins_mm.top"))

    def test_resolved_json_round_trips(self) -> None:
        style = style_resolver.resolve(genre="changelog", language="en-US")
        payload = json.dumps(style.to_json())
        self.assertIn("body.size_pt", payload)


class LanguageInferenceTests(TestCase):
    """The profile follows the document's language, not the alphabet.

    The resolver scored candidates on genre and language and broke ties on the
    profile's name. `-en` sorts before `-zh`, so asking for a one-pager without
    naming a language produced English typography for a Chinese document -- a
    wrong answer presented as a resolved style.
    """

    def test_a_genre_alone_resolves_through_the_template(self) -> None:
        # `one-pager.html` declares zh-CN, so the Chinese profile is the one
        # that fits a Chinese document.
        style = style_resolver.resolve(genre="one-pager")
        self.assertIn("zh", style.domains.get("typography", ""))

    def test_an_explicit_language_wins_over_the_template(self) -> None:
        style = style_resolver.resolve(genre="one-pager", language="en-US")
        self.assertIn("en", style.domains.get("typography", ""))

    def test_the_template_language_is_read_from_the_root_element(self) -> None:
        from pathlib import Path

        templates = Path(style_resolver.ROOT) / "assets" / "templates"
        self.assertEqual("zh-CN", style_resolver.language_of_template(templates / "one-pager.html"))
        self.assertEqual("en", style_resolver.language_of_template(templates / "one-pager-en.html"))

    def test_a_template_without_a_language_returns_none(self) -> None:
        self.assertIsNone(style_resolver.language_of_template(Path("/nonexistent.html")))

    def test_a_tie_is_reported_rather_than_broken_by_name(self) -> None:
        # Asked directly, without a language, two profiles fit equally and the
        # function says so instead of choosing.
        profiles, _ = style_resolver._load_profiles()
        choice, tied = style_resolver._best_match(
            profiles["typography"], "one-pager", False, None
        )
        self.assertIsNone(choice)
        self.assertEqual(2, len(tied))

    def test_a_language_settles_a_tie(self) -> None:
        profiles, _ = style_resolver._load_profiles()
        choice, tied = style_resolver._best_match(
            profiles["typography"], "one-pager", True, "zh-Hans-CN"
        )
        self.assertIsNotNone(choice)
        self.assertEqual([], tied)

    def test_the_template_for_a_genre_is_found(self) -> None:
        from pathlib import Path

        found = style_resolver.template_for_genre("one-pager")
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).is_file())

    def test_an_english_genre_finds_the_english_template(self) -> None:
        found = style_resolver.template_for_genre("one-pager", "en-US")
        self.assertIsNotNone(found)
        self.assertIn("-en", Path(found).name)
