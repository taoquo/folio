"""The layout plan: one value per role per width, and nothing decided in CSS.

The plan is the engine's answer to "what does this page compute to at 390px".
These tests hold it to that: every override is a value, every value comes from
the profile, the boundaries resolve the way the cascade does, and the
stylesheet cannot declare a width the plan does not know.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_plan  # noqa: E402
from projection import web_projection  # noqa: E402

BASE_CSS = ROOT / "assets" / "templates" / "web" / "base.css"


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = web_plan.viewport_plan("zh-Hans-CN")

    def test_every_override_is_a_value_and_names_its_source(self) -> None:
        for override in self.plan["overrides"]:
            with self.subTest(step=override["class"]):
                self.assertTrue(override["values"])
                for variable, item in override["values"].items():
                    self.assertTrue(variable.startswith("--web-"))
                    self.assertTrue(item["value"])
                    self.assertTrue(item["source"])

    def test_no_override_declares_a_viewport_qualified_name(self) -> None:
        # The qualifier is how the profile states the input. The page reads the
        # plain name, so a qualified one reaching a page would be a second
        # scale living beside the first.
        for override in self.plan["overrides"]:
            for variable in override["values"]:
                with self.subTest(variable=variable):
                    self.assertFalse(
                        any(f"-{q}-" in variable for q in ("compact", "narrow", "wide")),
                        variable)

    def test_the_regular_values_are_the_projected_ones(self) -> None:
        projected = web_projection(language="zh-Hans-CN").projected
        for name, item in self.plan["base"].items():
            with self.subTest(variable=name):
                self.assertEqual(projected[name], item["value"])

    def test_the_boundaries_resolve_like_the_cascade(self) -> None:
        cases = {
            390: {"--web-h1-size": "32px", "--web-kpi-columns": "1"},
            480: {"--web-h1-size": "32px", "--web-kpi-columns": "1"},
            481: {"--web-h1-size": "38px", "--web-kpi-columns": "2"},
            768: {"--web-h1-size": "38px", "--web-kpi-columns": "2"},
            769: {"--web-h1-size": "48px", "--web-kpi-columns": "4"},
            1279: {"--web-h1-size": "48px"},
            1280: {"--web-h1-size": "48px", "--web-figure-slot": "760px"},
        }
        for width, expected in cases.items():
            values = web_plan.resolve(self.plan, width)
            for name, want in expected.items():
                with self.subTest(width=width, variable=name):
                    self.assertEqual(want, values[name])

    def test_a_narrow_screen_lifts_the_measure_cap(self) -> None:
        # Below the compact step the page padding defines the column; a second
        # cap would put the figures on a different right edge than the text.
        for width in (390, 480, 768):
            with self.subTest(width=width):
                values = web_plan.resolve(self.plan, width)
                self.assertEqual("none", values["--web-measure-body"])
                self.assertEqual("none", values["--web-figure-slot"])

    def test_the_figure_band_matches_what_the_page_computes(self) -> None:
        g = web_plan.geometry("zh-Hans-CN")
        # Measured in Chromium: the column at 768, the slot at 1024 and 1414.
        self.assertEqual(676, web_plan.band_for(768, g))
        self.assertEqual(660, web_plan.band_for(1024, g))
        self.assertEqual(760, web_plan.band_for(1414, g))
        self.assertEqual(350, web_plan.band_for(390, g))

    def test_the_review_widths_cover_both_sides_of_every_breakpoint(self) -> None:
        for width in web_plan.BREAKPOINTS.values():
            with self.subTest(width=width):
                self.assertIn(width, web_plan.REVIEW_WIDTHS)
                self.assertIn(width - 1, web_plan.REVIEW_WIDTHS)


class PlanDocumentTests(unittest.TestCase):
    def test_the_document_states_a_value_for_every_review_width(self) -> None:
        document = web_plan.plan_document("zh-Hans-CN")

        self.assertEqual({str(w) for w in web_plan.REVIEW_WIDTHS},
                         set(document["viewports"]))
        for width, row in document["viewports"].items():
            with self.subTest(width=width):
                for key in ("class", "column", "band", "page_x", "h1_size",
                            "kpi_columns", "reading_size", "measure_capped"):
                    self.assertIn(key, row)
                self.assertLessEqual(row["band"], row["column"] + 0.01)

    def test_the_plan_is_deterministic(self) -> None:
        self.assertEqual(web_plan.plan_document("en"), web_plan.plan_document("en"))


class StylesheetTests(unittest.TestCase):
    def test_the_stylesheet_declares_no_unplanned_breakpoint(self) -> None:
        css = BASE_CSS.read_text(encoding="utf-8")

        self.assertEqual([], web_plan.stylesheet_breakpoints(css))

    def test_an_unplanned_breakpoint_is_caught(self) -> None:
        problems = web_plan.stylesheet_breakpoints("@media (max-width: 999px) { a { b: c; } }")

        self.assertEqual(1, len(problems))
        self.assertIn("999", problems[0])

    def test_a_breakpoint_may_change_arrangement_but_never_a_literal(self) -> None:
        # A media block may turn a numeral into a display element, reading a
        # role variable. It may not write a number: a size that appears at one
        # width belongs in the plan, which is what the page is verified against.
        css = BASE_CSS.read_text(encoding="utf-8")
        inside = False
        depth = 0
        offenders = []
        for line in css.splitlines():
            stripped = line.strip()
            if stripped.startswith("@media"):
                inside = True
                depth = 0
            if inside:
                depth += stripped.count("{") - stripped.count("}")
                match = re.match(r"(font-size|padding|margin|gap|line-height)\s*:\s*(.+)",
                                 stripped)
                if match and "var(" not in match.group(2) and match.group(2) not in {"0;"}:
                    offenders.append(stripped)
                if depth <= 0 and "}" in stripped:
                    inside = False
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
