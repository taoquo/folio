import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stabilize


class StabilizeNormalizationTests(TestCase):
    def test_rgba_is_flattened_onto_parchment(self) -> None:
        css, changed = stabilize.normalize_rgba("a { background: rgba(0, 0, 0, 0.5); }")

        self.assertEqual(1, changed)
        self.assertNotIn("rgba(", css)
        self.assertIn("#7B7875", css)

    def test_rgba_flattening_is_a_no_op_for_solid_hex(self) -> None:
        css, changed = stabilize.normalize_rgba("a { background: #F5F4ED; }")

        self.assertEqual(0, changed)
        self.assertEqual("a { background: #F5F4ED; }", css)

    def test_cool_grays_are_remapped_to_warm_neutrals(self) -> None:
        blocked = sorted(stabilize.COOL_GRAY_BLOCKLIST)[0]
        css, changed = stabilize.normalize_cool_grays(f"a {{ color: {blocked}; }}")

        self.assertEqual(1, changed)
        self.assertIn(css[css.index("#") : css.index("#") + 7], {"#4B3E39", "#87867F", "#E9DED4"})

    def test_line_heights_are_clamped_into_range(self) -> None:
        css, changed = stabilize.clamp_line_heights("a { line-height: 3.4; }\nb { line-height: 1.5; }", 1.2, 1.8)

        self.assertEqual(1, changed)
        self.assertIn("line-height: 1.8;", css)
        self.assertIn("line-height: 1.5;", css)

    def test_css_round_trip_preserves_surrounding_html(self) -> None:
        html = "<html><style>\na { color: red; }\n</style><body>x</body></html>"
        css, match = stabilize.extract_css(html)

        self.assertEqual("a { color: red; }", css.strip())
        self.assertEqual(html, stabilize.replace_css(html, css, match))

    def test_missing_style_block_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing <style> block"):
            stabilize.extract_css("<html><body>x</body></html>")


class StabilizeTargetResolutionTests(TestCase):
    def test_all_expands_to_every_html_target(self) -> None:
        self.assertEqual(list(stabilize.HTML_TARGETS), stabilize.resolve_targets(["all"]))
        self.assertEqual(list(stabilize.HTML_TARGETS), stabilize.resolve_targets([]))

    def test_source_file_names_work_as_aliases(self) -> None:
        self.assertEqual(["one-pager", "resume-en"], stabilize.resolve_targets(["one-pager.html", "resume-en"]))

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown target: slides"):
            stabilize.resolve_targets(["slides"])

    def test_every_target_points_at_an_existing_template(self) -> None:
        for target, (source, max_pages) in stabilize.HTML_TARGETS.items():
            self.assertTrue((stabilize.TEMPLATES / source).is_file(), target)
            self.assertGreater(max_pages, 0, target)


class StabilizeProfileValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profiles = stabilize.load_json(stabilize.PROFILES_FILE)

    def test_shipped_profiles_pass_validation_for_every_target(self) -> None:
        defaults = self.profiles.get("defaults", {})
        for target in stabilize.HTML_TARGETS:
            profile = stabilize.deep_merge(defaults, self.profiles.get("targets", {}).get(target, {}))
            stabilize.validate_profile(profile, target)

    def test_inverted_range_is_rejected(self) -> None:
        defaults = self.profiles.get("defaults", {})
        broken = stabilize.deep_merge(defaults, {"line_height": {"min": 2.0, "max": 1.0}})

        with self.assertRaisesRegex(ValueError, "line_height.min"):
            stabilize.validate_profile(broken, "one-pager")

    def test_non_numeric_range_bound_is_rejected(self) -> None:
        defaults = self.profiles.get("defaults", {})
        broken = stabilize.deep_merge(defaults, {"body_font_size_pt": {"min": "small", "max": 12}})

        with self.assertRaisesRegex(ValueError, "must be numeric"):
            stabilize.validate_profile(broken, "one-pager")


class StabilizationGateTests(TestCase):
    """The stabilizer must converge and must be a fixed point.

    A pass that keeps changing the same file makes `changed=True` meaningless,
    so idempotence is checked rather than assumed.
    """

    def setUp(self) -> None:
        self.profiles = stabilize.load_json(stabilize.PROFILES_FILE)
        self.tokens = {
            k: v
            for k, v in stabilize.load_json(stabilize.TOKENS_FILE).items()
            if isinstance(k, str) and isinstance(v, str)
        }
        self.defaults = self.profiles.get("defaults", {})
        self.targets_profiles = self.profiles.get("targets", {})

    def test_every_target_is_within_contract_and_idempotent(self) -> None:
        # Full coverage runs as `stabilize.py --check` in CI. This samples so
        # the unit suite stays fast: an exact-page contract and a ranged one.
        sample = ["resume", "changelog"]
        issues, results = stabilize.check_stabilization(
            sample, self.defaults, self.targets_profiles, self.tokens
        )
        self.assertEqual([], issues)
        self.assertEqual(sample, [r.target for r in results])

    def test_check_reports_no_overflow_for_constrained_targets(self) -> None:
        _, results = stabilize.check_stabilization(
            ["resume-en"], self.defaults, self.targets_profiles, self.tokens
        )
        for result in results:
            with self.subTest(target=result.target):
                self.assertIsNotNone(result.pages_after)
                self.assertLessEqual(result.pages_after, result.max_pages)

    def test_check_writes_nothing_into_the_templates(self) -> None:
        before = {t: (stabilize.TEMPLATES / s).read_bytes() for t, (s, _) in stabilize.HTML_TARGETS.items()}
        stabilize.check_stabilization(
            ["one-pager"], self.defaults, self.targets_profiles, self.tokens
        )
        after = {t: (stabilize.TEMPLATES / s).read_bytes() for t, (s, _) in stabilize.HTML_TARGETS.items()}
        self.assertEqual(before, after)

    def test_second_pass_leaves_an_already_normalized_file_untouched(self) -> None:
        # The property the gate relies on, checked directly on one target.
        import tempfile

        scratch = stabilize.ROOT / "dist" / "stabilize-check-test"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            first_dir, second_dir = Path(tmp) / "a", Path(tmp) / "b"
            # A template reaches its fonts as `../fonts/<file>`. Without that
            # path the renderer falls back to the template's remote font URL and
            # downloads a 24MB face, so the test would measure the network
            # instead of idempotence.
            fonts_link = Path(tmp) / "fonts"
            if not fonts_link.exists():
                fonts_link.symlink_to(
                    stabilize.ROOT / "assets" / "fonts", target_is_directory=True
                )
            source, max_pages = stabilize.HTML_TARGETS["resume"]
            profile = stabilize.deep_merge(self.defaults, self.targets_profiles.get("resume", {}))
            first = stabilize.run_for_target(
                "resume", source, max_pages, profile, self.tokens, False, first_dir, False
            )
            second = stabilize.run_for_target(
                "resume", source, max_pages, profile, self.tokens, False, second_dir, False,
                source_override=Path(first.output),
            )
            self.assertFalse(second.changed)
            self.assertEqual(Path(first.output).read_bytes(), Path(second.output).read_bytes())


class LayoutDecisionTests(TestCase):
    """Page fitting must be reviewable, not just visible.

    A solver step says a value moved. A decision says what it bought and what
    it cost, so a reviewer can question the expensive or pointless ones.
    """

    def test_a_step_is_turned_into_a_decision(self) -> None:
        steps = [stabilize.SolverStep("tighten_body_font", 10.0, 9.8, "pt", 3, 2)]
        decisions = stabilize.decisions_from_steps(steps, max_pages=2)
        self.assertEqual(1, len(decisions))
        decision = decisions[0]
        self.assertEqual("body_font_size_pt", decision.property)
        self.assertEqual(10.0, decision.value_from)
        self.assertEqual(9.8, decision.value_to)
        self.assertEqual(1, decision.pages_saved)

    def test_a_step_that_saved_nothing_is_marked_for_review(self) -> None:
        steps = [stabilize.SolverStep("tighten_section_gap", 18.0, 17.0, "pt", 3, 3)]
        decision = stabilize.decisions_from_steps(steps, max_pages=2)[0]
        self.assertEqual(0, decision.pages_saved)
        self.assertIn("without_gain", decision.reason)

    def test_reason_names_the_hard_contract_when_one_applies(self) -> None:
        steps = [stabilize.SolverStep("tighten_body_font", 9.2, 9.0, "pt", 3, 2)]
        decision = stabilize.decisions_from_steps(steps, max_pages=2)[0]
        self.assertEqual("hard_page_count_overflow", decision.reason)

    def test_action_order_reflects_typographic_cost(self) -> None:
        # Tightening a gap is cheaper than shrinking type; the solver spends
        # the cheap option first, so the costs must stay ordered that way.
        costs = stabilize.DECISION_COSTS
        self.assertLess(costs["tighten_section_gap"], costs["tighten_body_line_height"])
        self.assertLess(costs["tighten_body_line_height"], costs["tighten_body_font"])

    def test_every_solver_action_has_a_property_and_a_cost(self) -> None:
        actions = [
            "tighten_section_gap",
            "tighten_body_line_height",
            "tighten_body_font",
            "tighten_page_margin",
        ]
        for action in actions:
            with self.subTest(action=action):
                self.assertIn(action, stabilize.DECISION_COSTS)
                self.assertIn(action, stabilize.DECISION_PROPERTIES)

    def test_decision_serializes_for_a_build_artifact(self) -> None:
        steps = [stabilize.SolverStep("tighten_body_font", 10.0, 9.8, "pt", 3, 2)]
        payload = stabilize.decisions_from_steps(steps, max_pages=2)[0].to_json()
        self.assertEqual(
            {"decision", "property", "from", "to", "unit", "reason", "pages", "pages_saved", "cost"},
            set(payload),
        )
        json.dumps(payload)

    def test_target_result_exposes_decisions_and_a_summary(self) -> None:
        import json as _json
        import tempfile
        from pathlib import Path

        scratch = stabilize.ROOT / "dist" / "stabilize-check-test"
        scratch.mkdir(parents=True, exist_ok=True)
        profiles = stabilize.load_json(stabilize.PROFILES_FILE)
        tokens = {
            k: v
            for k, v in stabilize.load_json(stabilize.TOKENS_FILE).items()
            if isinstance(k, str) and isinstance(v, str)
        }
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            source, max_pages = stabilize.HTML_TARGETS["resume"]
            profile = stabilize.deep_merge(
                profiles["defaults"], profiles.get("targets", {}).get("resume", {})
            )
            result = stabilize.run_for_target(
                "resume", source, max_pages, profile, tokens, False, Path(tmp), False
            )
            payload = result.to_json()
        self.assertIn("layout_decisions", payload)
        self.assertIsInstance(payload["layout_decisions"], list)
        _json.dumps(payload)
