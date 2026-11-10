"""The checker fails on the page, and never passes by finding nothing.

A rule that reads an empty set as agreement is not a rule. These cases hold the
scanner half of `check_web.py` to that: every scan is given the input it is
supposed to catch, and an input it cannot judge is reported as SKIP rather than
counted as a pass.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_web  # noqa: E402


def tree(html: str) -> check_web.Node:
    parser = check_web.Tree()
    parser.feed(html)
    return parser.root


def styles(stylesheet: str) -> list[tuple[str, str, str]]:
    text = f"<style>{stylesheet}</style>"
    report = check_web.Report()
    check_web.check_styles(text, check_web.css_declarations(text), report)
    return [(rule, state, detail) for rule, state, detail in report.items]


def check(function, root: check_web.Node, source: str) -> list[tuple[str, str, str]]:
    report = check_web.Report()
    function(root, report, source)
    return [(rule, state, detail) for rule, state, detail in report.items]


class HexOutsideRootTests(unittest.TestCase):
    """W-COL-01 reads braces, not lines."""

    def test_a_one_line_root_does_not_hide_the_rules_after_it(self) -> None:
        self.assertEqual(
            ["line 2: #123456"],
            check_web.hex_outside_root(
                ":root { --x: #ffffff; }\n.a { color: #123456; }"))

    def test_a_rule_after_a_root_on_the_same_line_is_read(self) -> None:
        self.assertEqual(
            ["line 1: #eee"],
            check_web.hex_outside_root(".a { color: var(--x); } :root { --x: #fff; } "
                                       ".b { color: #eee; }"))

    def test_a_root_inside_a_media_query_is_still_root(self) -> None:
        self.assertEqual([], check_web.hex_outside_root(
            "@media (min-width: 40em) { :root { --x: #ffffff; } }"))
        self.assertEqual(["line 1: #ffffff"], check_web.hex_outside_root(
            "@media (min-width: 40em) { .a { color: #ffffff; } }"))

    def test_a_hex_in_a_comment_is_prose_not_a_declaration(self) -> None:
        self.assertEqual([], check_web.hex_outside_root(
            "/* accent #ff0000 */\n.a { color: var(--x); }"))

    def test_a_hex_shaped_id_is_a_selector(self) -> None:
        self.assertEqual([], check_web.hex_outside_root(
            "#abc { color: var(--x); }"))

    def test_a_colour_inside_a_shorthand_is_read(self) -> None:
        self.assertEqual(["line 1: #000"], check_web.hex_outside_root(
            ".a { border: 1px solid #000; }"))


class TemplateValueTests(unittest.TestCase):
    """W-DEN-08 reads every declaration, not a list of properties."""

    def assert_flagged(self, declaration: str) -> None:
        hits = [detail for rule, _state, detail in styles(declaration)
                if rule == "W-DEN-08"]
        self.assertTrue(hits and "none" not in hits[0], hits)

    def assert_clean(self, declaration: str) -> None:
        hits = [detail for rule, _state, detail in styles(declaration)
                if rule == "W-DEN-08"]
        self.assertEqual(["template-decided type/spacing values: none"], hits)

    def test_a_property_outside_the_old_list_is_read(self) -> None:
        self.assert_flagged(".a { letter-spacing: 2px; }")
        self.assert_flagged(".a { width: 40rem; }")

    def test_a_family_name_must_be_a_variable(self) -> None:
        self.assert_flagged(".a { font-family: Georgia, serif; }")
        self.assert_clean(".a { font-family: var(--serif); }")

    def test_a_literal_inside_a_media_query_is_read(self) -> None:
        # A conditional block is still a decision. `css_declarations` drops it
        # because the density checks read the base value; the literal scan
        # cannot use that view.
        self.assert_flagged("@media (min-width: 40em) { .a { padding: 4px; } }")
        self.assert_flagged(".a { color: var(--x); } "
                            "@media (max-width: 60em) { .a { gap: 2rem; } }")

    def test_a_media_prelude_and_a_font_face_are_not_declarations(self) -> None:
        self.assert_clean("@media (min-width: 40em) { :root { --x: 16px; } }")
        self.assert_clean('@font-face { font-family: "Source Serif 4"; }')

    def test_a_mixed_value_is_still_a_literal(self) -> None:
        # A value that reads one token is not thereby decided: the other half
        # is a length the template wrote itself.
        self.assert_flagged(".a { padding: 10px var(--web-space-3); }")

    def test_a_weight_is_a_type_value(self) -> None:
        self.assert_flagged(".a { font-weight: 600; }")
        self.assert_flagged(".a { font-weight: bold; }")
        self.assert_clean(".a { font-weight: var(--web-weight-medium); }")

    def test_a_ratio_is_not_a_fixed_length(self) -> None:
        self.assert_clean(".a { line-height: 1.5; }")
        self.assert_clean(".a { width: 100%; }")
        self.assert_clean(".a { grid-template-columns: 1fr 1fr; }")
        self.assert_clean(".a { max-width: calc(100vw - var(--x) * 2); }")
        self.assert_clean(".a { transition: color 0.18s ease; }")

    def test_the_two_gates_share_one_rule(self) -> None:
        # `projection.py check` reads the template source and `check_web.py`
        # reads the built page; a literal one gate sees and the other does not
        # is the failure this rule exists to close.
        import web_contracts

        for prop, value in (("padding", "10px var(--x)"), ("font-family", "Georgia"),
                            ("font-weight", "600"), ("width", "40rem"),
                            ("line-height", "1.5"), ("width", "100%"),
                            ("max-width", "calc(100vw - var(--x) * 2)")):
            with self.subTest(prop=prop, value=value):
                flagged = web_contracts.template_value_literal(prop, value)
                built = [detail for name, _state, detail in
                         styles(f".a {{ {prop}: {value}; }}") if name == "W-DEN-08"]
                self.assertEqual(flagged, "none" not in built[0])

    def test_the_shipped_template_declares_no_value(self) -> None:
        css = (ROOT / "assets" / "templates" / "web" / "base.css").read_text(
            encoding="utf-8")
        # The template is read before projection, so the variables it reads are
        # not defined by it; only the literals are under test.
        hits = [detail for rule, _state, detail in styles(css) if rule == "W-DEN-08"]
        self.assertEqual(["template-decided type/spacing values: none"], hits)


class SourceCoverageTests(unittest.TestCase):
    """W-CNT-01 counts Han runs, not only Latin words."""

    SOURCE = "注意力机制是所有现代语言模型的核心。编码器和解码器都使用多头注意力。"

    def test_a_chinese_source_is_measured(self) -> None:
        rows = check(check_web.check_content,
                     tree(f"<body><p>{self.SOURCE}</p></body>"), self.SOURCE)
        self.assertEqual([("W-CNT-01", "PASS",
                           "source word coverage 1.000 (0 missing)")], rows)

    def test_a_dropped_sentence_fails(self) -> None:
        rows = check(check_web.check_content,
                     tree("<body><p>注意力机制是所有现代语言模型的核心。</p></body>"),
                     self.SOURCE)
        self.assertEqual("FAIL", rows[0][1])

    def test_inline_markup_does_not_split_a_phrase(self) -> None:
        rows = check(check_web.check_content,
                     tree("<body><p>注意力机制是所有<strong>现代</strong>语言模型的核心。"
                          "编码器和解码器都使用多头注意力。</p></body>"), self.SOURCE)
        self.assertEqual("PASS", rows[0][1])

    def test_a_source_with_no_words_is_skipped_not_passed(self) -> None:
        rows = check(check_web.check_content, tree("<body><p>x</p></body>"), "。；！")
        self.assertEqual("SKIP", rows[0][1])


class ComponentScanTests(unittest.TestCase):
    """W-CNT-02 does not call an empty set of hits componentized."""

    def test_a_source_with_no_scanned_feature_is_skipped(self) -> None:
        rows = check(check_web.check_components, tree("<body><p>x</p></body>"),
                     "一段没有任何组件的说明文字。")
        self.assertEqual("SKIP", rows[0][1])

    def test_a_hit_that_is_not_on_the_page_fails(self) -> None:
        rows = check(check_web.check_components, tree("<body><p>x</p></body>"),
                     "① first step")
        self.assertEqual("FAIL", rows[0][1])


class ManifestDiscoveryTests(unittest.TestCase):
    """The documented command finds the manifest the builder wrote."""

    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        (self.root / "figures.manifest.json").write_text("{}", encoding="utf-8")
        (self.root / "module").mkdir()
        (self.root / "module" / "index.html").write_text("", encoding="utf-8")
        (self.root / "index.html").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_a_module_page_finds_the_series_manifest(self) -> None:
        self.assertEqual(self.root / "figures.manifest.json",
                         check_web.discover_manifest(
                             self.root / "module" / "index.html", None))

    def test_the_series_index_finds_it_beside_itself(self) -> None:
        self.assertEqual(self.root / "figures.manifest.json",
                         check_web.discover_manifest(self.root / "index.html", None))

    def test_a_page_outside_a_series_has_none(self) -> None:
        other = self.root / "module" / "copy.html"
        other.write_text("", encoding="utf-8")
        (self.root / "figures.manifest.json").unlink()
        self.assertIsNone(check_web.discover_manifest(other, None))


class AcceptanceMappingTests(unittest.TestCase):
    """Each acceptance row names every rule its reference table names."""

    def rows(self) -> dict[str, list[str]]:
        # The mapping is a local inside `acceptance`; read it from the source so
        # the test fails when a row is added without its rule, not when the
        # implementation happens to change shape.
        import ast

        source = (ROOT / "scripts" / "check_web.py").read_text(encoding="utf-8")
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "acceptance")
        assignment = next(node for node in ast.walk(function)
                          if isinstance(node, ast.Assign)
                          and getattr(node.targets[0], "id", "") == "mapping")
        return {key.value: [item.value for item in value.elts]
                for key, value in zip(assignment.value.keys, assignment.value.values)}

    def test_the_block_rules_carry_their_own_ids(self) -> None:
        self.assertIn("W-CNT-04", self.rows()["no-purple"])

    def test_the_table_row_carries_the_arrow_rule(self) -> None:
        self.assertIn("W-DEN-07", self.rows()["table-shape"])

    def test_every_row_maps_at_least_one_rule(self) -> None:
        for key, rules in self.rows().items():
            with self.subTest(row=key):
                self.assertTrue(rules)

    def test_every_mapped_rule_is_emitted_by_the_checker(self) -> None:
        source = (ROOT / "scripts" / "check_web.py").read_text(encoding="utf-8")
        for key, rules in self.rows().items():
            for rule in rules:
                with self.subTest(row=key, rule=rule):
                    self.assertIn(f'"{rule}"', source)


if __name__ == "__main__":
    unittest.main()
