"""Spacing is a decision, not a computation.

The plan's central question about layout is "why is there this much space
between these two blocks". A spacing model that cannot answer it has moved the
numbers without making them explainable.

These tests hold the model to three properties: every gap names the rule that
produced it, an unlisted pair is visible rather than silently comfortable, and
elastic behaviour is declared rather than assumed.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import spacing  # noqa: E402
from spacing import Length, SpaceSpec, SpacingError  # noqa: E402


class LengthTests(TestCase):
    def test_a_length_requires_a_unit(self) -> None:
        with self.assertRaises(TypeError):
            Length(6)  # type: ignore[call-arg]

    def test_an_unknown_unit_is_refused(self) -> None:
        with self.assertRaises(SpacingError):
            Length(6, "furlong")  # type: ignore[arg-type]

    def test_a_negative_length_is_refused(self) -> None:
        with self.assertRaises(SpacingError):
            Length(-1, "pt")

    def test_em_is_relative_to_this_documents_type_size(self) -> None:
        # 1em at 10pt body size is 10pt, not 16px. Assuming a browser default
        # would make the conversion wrong for every Folio document.
        self.assertEqual(10.0, Length(1, "em").as_pt(base_pt=10.0))
        self.assertEqual(12.0, Length(1, "em").as_pt(base_pt=12.0))

    def test_units_convert_to_points(self) -> None:
        self.assertEqual(6.0, Length(6, "pt").as_pt())
        self.assertAlmostEqual(0.75, Length(1, "px").as_pt())
        self.assertAlmostEqual(72.0, Length(25.4, "mm").as_pt(), places=6)


class SpecTests(TestCase):
    def test_min_above_preferred_is_refused(self) -> None:
        with self.assertRaises(SpacingError):
            SpaceSpec(preferred=Length(4, "pt"), min=Length(8, "pt"))

    def test_max_below_preferred_is_refused(self) -> None:
        with self.assertRaises(SpacingError):
            SpaceSpec(preferred=Length(8, "pt"), max=Length(4, "pt"))

    def test_mixed_units_are_refused(self) -> None:
        # Comparing 4pt with 1em needs a document, which the spec does not have.
        with self.assertRaises(SpacingError):
            SpaceSpec(preferred=Length(4, "pt"), min=Length(1, "em"))

    def test_strength_maps_to_a_readable_priority(self) -> None:
        self.assertGreater(
            SpaceSpec(preferred=Length(4, "pt"), strength="required").priority,
            SpaceSpec(preferred=Length(4, "pt"), strength="weak").priority,
        )

    def test_an_unknown_strength_is_refused(self) -> None:
        with self.assertRaises(SpacingError):
            SpaceSpec(preferred=Length(4, "pt"), strength="very")


class ResolutionTests(TestCase):
    def test_a_declared_pair_uses_its_own_rule(self) -> None:
        gap = spacing.resolve_gap("heading", "paragraph")
        self.assertEqual("heading->paragraph", gap.rule)
        self.assertEqual(6.0, gap.spec.preferred.value)

    def test_an_undeclared_pair_is_visible(self) -> None:
        # The fallback exists so a gap is never undefined, but it is marked weak
        # and named, because an unlisted pair is a gap in the rules.
        gap = spacing.resolve_gap("table", "table")
        self.assertEqual("fallback", gap.rule)
        self.assertTrue(gap.is_fallback)
        self.assertEqual("weak", gap.spec.strength)

    def test_context_adjusts_rather_than_replaces(self) -> None:
        plain = spacing.resolve_gap("paragraph", "heading")
        opened = spacing.resolve_gap("paragraph", "heading", context=("section-opening",))
        self.assertGreater(opened.spec.preferred.value, plain.spec.preferred.value)
        self.assertEqual("contextual", opened.spec.kind)
        self.assertEqual(("section-opening",), opened.context)

    def test_context_does_not_soften_a_hard_constraint(self) -> None:
        gap = spacing.resolve_gap("figure", "caption", context=("dense",))
        self.assertEqual("hard", gap.spec.constraint)

    def test_node_types_are_normalised(self) -> None:
        for alias, expected in (("h2", "heading"), ("p", "paragraph"),
                                ("li", "list_item"), ("img", "figure")):
            with self.subTest(alias=alias):
                self.assertEqual(expected, spacing.normalise(alias))

    def test_an_alias_resolves_to_the_canonical_rule(self) -> None:
        self.assertEqual(
            spacing.resolve_gap("heading", "paragraph").spec.preferred.value,
            spacing.resolve_gap("h1", "p").spec.preferred.value,
        )

    def test_every_rule_is_documented(self) -> None:
        for (left, right), spec in spacing.BASE_RULES.items():
            with self.subTest(pair=f"{left}->{right}"):
                self.assertTrue(spec.note, "a rule with no stated reason cannot be reviewed")

    def test_elastic_behaviour_is_declared(self) -> None:
        gap = spacing.resolve_gap("paragraph", "paragraph")
        self.assertTrue(gap.spec.elastic)
        payload = gap.to_json()
        self.assertIn("stretch", payload["spec"])

    def test_explanation_names_the_rule_and_the_reason(self) -> None:
        text = spacing.resolve_gap("figure", "caption").explain()
        self.assertIn("figure -> caption", text)
        self.assertIn("hard", text)

    def test_an_elastic_gap_says_a_backend_must_report_it(self) -> None:
        text = spacing.resolve_gap("paragraph", "paragraph").explain()
        self.assertIn("must report", text)


class TemplateAuditTests(TestCase):
    def test_the_audit_finds_margin_declarations(self) -> None:
        payload = spacing.audit_template(ROOT / "assets" / "templates" / "one-pager.html")
        self.assertGreater(payload["declarations"], 0)
        self.assertTrue(payload["values"])

    def test_a_missing_template_is_reported(self) -> None:
        payload = spacing.audit_template(ROOT / "assets" / "templates" / "no-such.html")
        self.assertIn("error", payload)
