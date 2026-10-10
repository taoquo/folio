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
