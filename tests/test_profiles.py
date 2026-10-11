"""Profiles must describe the repository as it is.

A profile that disagrees with the templates is worse than none: it documents a
system that does not exist. These tests pin both the shipped profiles and the
rules that would catch a drifted one.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import profile_check as pc


class ShippedProfileTests(TestCase):
    def test_profiles_validate_against_the_repository(self) -> None:
        report = pc.run_checks()
        self.assertEqual([], [f.message for f in report.errors])

    def test_all_five_profile_kinds_are_present(self) -> None:
        report = pc.run_checks()
        self.assertEqual(5, report.checked.get("profile_kinds"))

    def test_every_genre_has_a_page_profile(self) -> None:
        profiles = pc.load_profiles()
        genres = {body.get("genre") for body in profiles["page"].values()}
        for genre in ("one-pager", "letter", "long-doc", "portfolio", "resume",
                      "equity-report", "changelog", "slides"):
            with self.subTest(genre=genre):
                self.assertIn(genre, genres)

    def test_hard_page_contracts_match_the_build_table(self) -> None:
        # The profile and page_contracts.py must agree on which genres are exact.
        from page_contracts import HTML_TARGETS

        profiles = pc.load_profiles()
        by_genre = {b.get("genre"): b for b in profiles["page"].values()}
        for target, spec in HTML_TARGETS.items():
            if target.endswith("-en"):
                continue
            entry = by_genre.get(target)
            if entry is None:
                continue
            mode = (entry.get("page_count") or {}).get("mode")
            exact = spec.min_pages == spec.max_pages
            with self.subTest(genre=target):
                self.assertEqual("hard" if exact else mode, "hard" if exact else mode)
                if exact:
                    self.assertEqual("hard", mode)
                    self.assertEqual(spec.max_pages, (entry.get("page_count") or {}).get("exact"))


class ProfileRuleTests(TestCase):
    def _report_for(self, kind: str, name: str, body: dict) -> pc.Report:
        """Structure-check one profile, with the other kinds populated.

        `check_structure` also guards against a whole kind parsing to nothing,
        so the fixture fills the other kinds to keep each test focused on the
        rule it names.
        """
        report = pc.Report()
        profiles = {
            "typography": {"base": {"body": {"size_pt": 10}}},
            "page": {"base": {"page_count": {"mode": "soft", "target": 1}}},
            "language": {"base": {"tag": "en-US"}},
            "theme": {"base": {"colors": {"paper": "#F6F0EA"}}},
            "taste": {"base": {"hard_requirements": {"overflow": 0}}},
        }
        profiles[kind] = {name: body}
        pc.check_structure(profiles, report)
        return report

    def test_hard_page_count_requires_exact(self) -> None:
        report = self._report_for("page", "p", {"page_count": {"mode": "hard"}})
        self.assertTrue(any(f.code == "PROFILE.PAGE.HARD_NO_EXACT" for f in report.errors))

    def test_soft_page_count_requires_target(self) -> None:
        report = self._report_for("page", "p", {"page_count": {"mode": "soft"}})
        self.assertTrue(any(f.code == "PROFILE.PAGE.SOFT_NO_TARGET" for f in report.errors))

    def test_unknown_page_mode_is_rejected(self) -> None:
        report = self._report_for("page", "p", {"page_count": {"mode": "maybe"}})
        self.assertTrue(any(f.code == "PROFILE.PAGE.NO_MODE" for f in report.errors))

    def test_typography_without_body_is_rejected(self) -> None:
        report = self._report_for("typography", "t", {"genre": "x"})
        self.assertTrue(any(f.code == "PROFILE.TYPO.NO_BODY" for f in report.errors))

    def test_taste_rejects_a_requirement_in_both_lists(self) -> None:
        report = self._report_for(
            "taste", "t",
            {"hard_requirements": {"figure_alt": "required"},
             "soft_objectives": {"figure_alt": "preferred"}},
        )
        self.assertTrue(any(f.code == "PROFILE.TASTE.OVERLAP" for f in report.errors))

    def test_taste_hard_and_soft_stay_distinguishable(self) -> None:
        report = self._report_for(
            "taste", "t",
            {"hard_requirements": {"figure_alt": "required"},
             "soft_objectives": {"ornament": "minimal"}},
        )
        self.assertEqual([], report.errors)

    def test_type_properties_in_theme_are_rejected(self) -> None:
        report = pc.Report()
        pc.check_separation({"theme": {"x": {"size_pt": 10}}}, report)
        self.assertTrue(any(f.code == "PROFILE.SEPARATION.TYPE_IN_THEME" for f in report.errors))

    def test_colour_in_typography_is_rejected(self) -> None:
        report = pc.Report()
        pc.check_separation({"typography": {"x": {"brand": "#B83D2E"}}}, report)
        self.assertTrue(any(f.code == "PROFILE.SEPARATION.COLOR_IN_TYPO" for f in report.errors))


class InheritanceTests(TestCase):
    def test_child_inherits_parent_fields(self) -> None:
        report = pc.Report()
        profiles = {"base": {"body": {"size_pt": 10.5, "leading": 1.55}}, "child": {"extends": "base", "genre": "x"}}
        resolved = pc._resolve_extends(profiles, "typography", report)
        self.assertEqual(10.5, resolved["child"]["body"]["size_pt"])
        self.assertNotIn("extends", resolved["child"])

    def test_child_overrides_parent_value(self) -> None:
        report = pc.Report()
        profiles = {"base": {"body": {"size_pt": 10.5}}, "child": {"extends": "base", "body": {"size_pt": 9.2}}}
        resolved = pc._resolve_extends(profiles, "typography", report)
        self.assertEqual(9.2, resolved["child"]["body"]["size_pt"])

    def test_unknown_parent_is_reported(self) -> None:
        report = pc.Report()
        pc._resolve_extends({"child": {"extends": "nope"}}, "typography", report)
        self.assertTrue(any(f.code == "PROFILE.EXTENDS.UNKNOWN" for f in report.errors))

    def test_cycle_is_reported_rather_than_hanging(self) -> None:
        report = pc.Report()
        pc._resolve_extends({"a": {"extends": "b"}, "b": {"extends": "a"}}, "typography", report)
        self.assertTrue(any(f.code == "PROFILE.EXTENDS.CYCLE" for f in report.errors))


class TemplateMetricTests(TestCase):
    def test_body_metrics_are_read_from_a_template(self) -> None:
        size, leading = pc._template_body_metrics(ROOT / "assets" / "templates" / "one-pager.html")
        self.assertAlmostEqual(10.0, size)
        self.assertAlmostEqual(1.45, leading)

    def test_combined_selector_is_not_mistaken_for_body(self) -> None:
        # `html, body { background: ... }` sets the canvas, not the text size.
        size, leading = pc._template_body_metrics(ROOT / "assets" / "templates" / "resume.html")
        self.assertIsNotNone(size)
        self.assertAlmostEqual(9.2, size, places=2)


class ProfileCoverageGuardTests(TestCase):
    """A whole profile kind going missing must fail, not pass quietly.

    The taste set was invisible for a while because its file used `contracts:`
    instead of `profiles:` as the top-level key. Nothing noticed.
    """

    def test_every_kind_parses_at_least_one_profile(self) -> None:
        profiles = pc.load_profiles()
        for kind in ("typography", "page", "language", "theme", "taste"):
            with self.subTest(kind=kind):
                self.assertIn(kind, profiles)
                self.assertTrue(profiles[kind], f"{kind} parsed no profiles")

    def test_empty_kind_is_reported_as_an_error(self) -> None:
        report = pc.Report()
        pc.check_structure({"typography": {"a": {"body": {"size_pt": 10}}}, "page": {}, "language": {},
                            "theme": {}, "taste": {}}, report)
        codes = {f.code for f in report.errors}
        self.assertIn("PROFILE.KIND.EMPTY", codes)

    def test_wrong_top_level_key_yields_an_empty_kind(self) -> None:
        # The exact failure mode that hid the taste contracts.
        parsed = pc.parse_yaml("version: 1\ncontracts:\n  a:\n    genre: x\n")
        self.assertEqual({}, parsed.get("profiles") or {})


class ParagraphRuleTests(TestCase):
    """Paragraph flow rules were declared in the profile but set nowhere.

    That is the failure mode this checks for: a profile describing a document
    that does not exist.
    """

    def test_templates_declare_the_flow_rules_the_profile_requires(self) -> None:
        for filename in ("resume.html", "resume-en.html", "long-doc.html",
                         "one-pager.html", "letter.html"):
            with self.subTest(template=filename):
                rules = pc._template_paragraph_rules(ROOT / "assets" / "templates" / filename)
                self.assertEqual(2, rules.get("widows"))
                self.assertEqual(2, rules.get("orphans"))
                self.assertEqual("manual", rules.get("hyphens"))

    def test_a_template_without_flow_rules_reads_as_empty(self) -> None:
        # A rule on the canvas or screen-shell block must not be picked up.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.html"
            path.write_text(
                "<style>\n"
                "  html, body { widows: 4; }\n"
                "  body { font-family: var(--serif); font-size: 10pt; }\n"
                "  @media screen { body { widows: 9; } }\n"
                "</style>\n"
            )
            rules = pc._template_paragraph_rules(path)
            self.assertNotIn("widows", rules)

    def test_rules_are_read_from_the_main_body_block(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.html"
            path.write_text(
                "<style>\n"
                "  html, body { widows: 4; }\n"
                "  body { font-family: var(--serif); widows: 2; orphans: 2; hyphens: manual; }\n"
                "</style>\n"
            )
            rules = pc._template_paragraph_rules(path)
            self.assertEqual(2, rules.get("widows"))
            self.assertEqual("manual", rules.get("hyphens"))

    def test_profile_check_reports_a_missing_declaration(self) -> None:
        report = pc.Report()
        with __import__("tempfile").TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.html"
            path.write_text("<style>\n  body { font-family: var(--serif); font-size: 10pt; }\n</style>\n")
            rules = pc._template_paragraph_rules(path)
            if rules.get("widows") is None:
                report.error("PROFILE.PARAGRAPH.NOT_SET", "test", "no widows declared")
        self.assertTrue(any(f.code == "PROFILE.PARAGRAPH.NOT_SET" for f in report.errors))


class CommentStrippingTests(TestCase):
    """A hash inside a string is not a comment.

    The profile parser removed comments with `split("#", 1)[0]`, which also cut
    a `#` inside a quoted value. Every hex colour in the theme profile is
    written `paper: "#F6F0EA"`, so all fifteen loaded as empty strings: the
    profile was defined, read, and had no effect on a page.
    """

    def test_a_quoted_hash_survives(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml('paper: "#F6F0EA"\n')
        self.assertEqual("#F6F0EA", parsed["paper"])

    def test_a_trailing_comment_still_goes(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml('paper: "#F6F0EA"   # the canvas\n')
        self.assertEqual("#F6F0EA", parsed["paper"])

    def test_a_hash_inside_a_flow_mapping_survives(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml('rule: {ink: "#191514", paper: "#F6F0EA"}  # colours\n')
        self.assertEqual("#191514", parsed["rule"]["ink"])
        self.assertEqual("#F6F0EA", parsed["rule"]["paper"])

    def test_an_unquoted_hash_still_starts_a_comment(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml("note: plain   # explanation\n")
        self.assertEqual("plain", parsed["note"])

    def test_a_whole_line_comment_is_ignored(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml("# leading comment\nkey: value\n")
        self.assertEqual({"key": "value"}, parsed)

    def test_single_quotes_are_tracked_too(self) -> None:
        from profile_check import parse_yaml

        parsed = parse_yaml("paper: '#F6F0EA'  # ok\n")
        self.assertEqual("#F6F0EA", parsed["paper"])


class ParserParityTests(TestCase):
    """The profile parser and a standards parser agree on every shipped file.

    The parser is hand-written, so nothing stops it drifting from YAML. Where
    the two disagree the file is ambiguous and a reader would guess, which is
    worth knowing before it reaches a profile.
    """

    def test_every_profile_parses_the_same_way(self) -> None:
        import glob

        import profile_check
        import yaml

        def flatten(node, path=""):
            out = {}
            if isinstance(node, dict):
                for key, value in node.items():
                    out.update(flatten(value, f"{path}.{key}" if path else key))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    out.update(flatten(value, f"{path}[{index}]"))
            else:
                out[path] = node
            return out

        root = Path(__file__).resolve().parents[1]
        differences = []
        for name in sorted(glob.glob(str(root / "references" / "profiles" / "**" / "*.yaml"),
                                     recursive=True)):
            text = Path(name).read_text(encoding="utf-8")
            mine = flatten(profile_check.parse_yaml(text))
            theirs = flatten(yaml.safe_load(text))
            for key, value in theirs.items():
                if key in mine and mine[key] != value:
                    differences.append(f"{Path(name).name}:{key}")

        self.assertEqual([], differences)


class ParserParityWithCorpusTests(TestCase):
    """The two hand-written YAML readers agree.

    `corpus._parse_yaml` and `profile_check.parse_yaml` duplicate each other
    closely, and a block sequence written at its key's own indentation was
    misread as an empty mapping by both. The bug was found once and had to be
    fixed twice; this fails if the next one lands in only one of them.
    """

    def test_both_readers_agree_on_a_profile_file(self) -> None:
        import corpus
        import profile_check

        root = Path(__file__).resolve().parents[1]
        for name in sorted((root / "references" / "profiles").rglob("*.yaml")):
            with self.subTest(profile=name.name):
                text = name.read_text(encoding="utf-8")
                self.assertEqual(corpus._parse_yaml(text), profile_check.parse_yaml(text))

    def test_both_accept_a_sequence_at_its_key_indentation(self) -> None:
        import corpus
        import profile_check

        sample = "a:\n  b:\n  - one\n  - two\n  c: 1\n"
        expected = {"a": {"b": ["one", "two"], "c": 1}}
        self.assertEqual(expected, corpus._parse_yaml(sample))
        self.assertEqual(expected, profile_check.parse_yaml(sample))
