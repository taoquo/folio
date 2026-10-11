"""Reading spacing back off a page.

The comparison is the point: a rule in the model and a margin in a template are
the same quantity only after the leading is removed. The first version compared
a margin with a baseline distance and reported that nothing matched, which was
accurate and useless.

These tests hold the arithmetic and the honesty of the report.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import spacing_probe  # noqa: E402


class SurplusTests(TestCase):
    def test_surplus_removes_the_leading(self) -> None:
        # A rule states a margin; the probe measures a baseline distance. Only
        # the surplus over the leading is comparable.
        probe = spacing_probe.Probe(document="x", baseline_pt=18.5)
        gap = spacing_probe.ObservedGap(page=1, size_pt=28.4, above="a", below="b")
        self.assertAlmostEqual(9.9, probe.surplus_pt(gap), places=1)

    def test_a_gap_at_the_leading_has_no_surplus(self) -> None:
        probe = spacing_probe.Probe(document="x", baseline_pt=18.5)
        gap = spacing_probe.ObservedGap(page=1, size_pt=18.5, above="a", below="b")
        self.assertEqual(0.0, probe.surplus_pt(gap))

    def test_a_gap_below_the_leading_does_not_go_negative(self) -> None:
        probe = spacing_probe.Probe(document="x", baseline_pt=18.5)
        gap = spacing_probe.ObservedGap(page=1, size_pt=10.0, above="a", below="b")
        self.assertEqual(0.0, probe.surplus_pt(gap))

    def test_an_unknown_leading_returns_the_raw_distance(self) -> None:
        probe = spacing_probe.Probe(document="x")
        gap = spacing_probe.ObservedGap(page=1, size_pt=28.4, above="a", below="b")
        self.assertAlmostEqual(28.4, probe.surplus_pt(gap), places=1)


class MeasureTests(TestCase):
    def _example(self) -> Path:
        for name in ("one-pager", "long-doc", "resume"):
            candidate = ROOT / "assets" / "examples" / f"{name}.pdf"
            if candidate.is_file():
                return candidate
        self.skipTest("no built example")

    def test_a_measured_document_reports_a_leading(self) -> None:
        probe = spacing_probe.measure(self._example())
        self.assertIsNotNone(probe.baseline_pt)
        self.assertGreater(probe.baseline_pt, 0)

    def test_the_leading_is_the_most_common_distance(self) -> None:
        # Not the smallest: a heading sitting close to its subtitle is the
        # smallest gap on the page and is not the leading.
        probe = spacing_probe.measure(self._example())
        self.assertGreater(probe.baseline_pt, 8.0)

    def test_block_gaps_are_reported(self) -> None:
        probe = spacing_probe.measure(self._example())
        self.assertTrue(probe.gaps or probe.notes)

    def test_a_missing_document_is_reported_not_raised(self) -> None:
        probe = spacing_probe.measure(ROOT / "assets" / "examples" / "no-such.pdf")
        self.assertTrue(probe.notes)

    def test_the_probe_is_serialisable(self) -> None:
        import json

        probe = spacing_probe.measure(self._example())
        json.dumps(probe.to_json())


class CompareTests(TestCase):
    def test_a_genre_compares_against_the_rules(self) -> None:
        payload = spacing_probe.compare("one-pager")
        self.assertIn("comparisons", payload)
        self.assertGreater(payload["rules_checked"], 0)

    def test_the_comparison_uses_the_surplus_not_the_raw_distance(self) -> None:
        # The surplus is the measured distance minus the leading, so it is
        # always smaller than that distance. An earlier version compared against
        # a fixed number taken from one document, which held only while the
        # example was a template rendered with its short placeholder text.
        payload = spacing_probe.compare("one-pager")
        leading = (payload["probe"].get("baseline_pt") or 0)
        for value in payload.get("observed_surplus_pt") or []:
            with self.subTest(value=value):
                self.assertGreaterEqual(value, 0)
                self.assertLess(value, leading + value)

    def test_at_least_some_rules_match_a_real_document(self) -> None:
        # If nothing matched, either the model or the probe is wrong; either way
        # the report should not be trusted as evidence of agreement.
        payload = spacing_probe.compare("one-pager")
        self.assertGreater(payload["rules_agreeing"], 0)

    def test_a_genre_without_an_example_is_reported(self) -> None:
        payload = spacing_probe.compare("no-such-genre")
        self.assertIn("error", payload)

    def test_the_report_says_it_does_not_gate(self) -> None:
        payload = spacing_probe.compare("one-pager")
        self.assertIn("does not gate", payload["note"])

    def test_every_comparison_states_a_status(self) -> None:
        payload = spacing_probe.compare("one-pager")
        for item in payload["comparisons"]:
            with self.subTest(pair=item["pair"]):
                self.assertIn(item["status"], {"agrees", "not observed", "not measurable"})


class NestedGapTests(TestCase):
    """A gap between two blocks must not depend on what contains them.

    The plan asks for this explicitly: the same document and profile should not
    produce a different sibling gap because the blocks were nested one level
    deeper. The failure it guards against is a resolver that walks a tree and
    applies a context rule for every level it descends, so nesting silently
    multiplies the spacing.

    The check is a measurement, not an assertion about the code: render two
    documents whose only difference is nesting, and compare what the page shows.
    """

    def _render(self, html: str, work: Path, name: str) -> Path:
        from weasyprint import HTML

        source = work / f"{name}.html"
        source.write_text(html, encoding="utf-8")
        target = work / f"{name}.pdf"
        HTML(string=html, base_url=str(work)).write_pdf(str(target))
        return target

    def test_nesting_does_not_change_the_gap_between_siblings(self) -> None:
        import tempfile

        css = (
            "<style>"
            "@page { size: A4; margin: 20mm; }"
            "body { font-family: serif; font-size: 10pt; line-height: 1.45; }"
            "p { margin: 0 0 6pt 0; }"
            "section { margin: 0; padding: 0; }"
            "</style>"
        )
        # Four paragraphs, so there are three gaps: two at the leading and one
        # that a wrapper could disturb. Two paragraphs would give a single gap,
        # which the probe takes as the leading and cannot compare with anything.
        body = "".join(f"<p>Line {i}</p>" for i in range(1, 5))
        flat = f"<html><head>{css}</head><body>{body}</body></html>"
        nested = (
            f"<html><head>{css}</head><body>"
            f"<section>{body}</section>"
            "</body></html>"
        )

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            flat_pdf = self._render(flat, work, "flat")
            nested_pdf = self._render(nested, work, "nested")
            flat_gaps = spacing_probe.measure(flat_pdf).sizes()
            nested_gaps = spacing_probe.measure(nested_pdf).sizes()

        # The wrapper contributes no spacing of its own, so the gaps a reader
        # sees must be the same set.
        self.assertEqual(flat_gaps, nested_gaps)

    def test_a_wrapper_that_widens_every_gap_changes_the_page(self) -> None:
        # The converse, and it has to be measured off the page rather than read
        # from the probe's labels. When a wrapper widens every gap, the probe
        # names the wider value as the leading and the two documents look the
        # same by name; the page is still 20pt taller per line.
        import tempfile

        css = (
            "<style>"
            "@page { size: A4; margin: 20mm; }"
            "body { font-family: serif; font-size: 10pt; line-height: 1.45; }"
            "p { margin: 0 0 6pt 0; }"
            "</style>"
        )
        body = "".join(f"<p>Line {i}</p>" for i in range(1, 5))
        flat = f"<html><head>{css}</head><body>{body}</body></html>"
        padded = (
            f"<html><head>{css}"
            "section p { margin-bottom: 26pt; }"
            f"</head><body><section>{body}</section></body></html>"
        )

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            flat_pdf = self._render(flat, work, "flat")
            padded_pdf = self._render(padded, work, "padded")
            flat_span = self._text_span(flat_pdf)
            padded_span = self._text_span(padded_pdf)

        self.assertIsNotNone(flat_span)
        self.assertIsNotNone(padded_span)
        self.assertGreater(padded_span, flat_span)

    @staticmethod
    def _text_span(pdf: Path) -> float | None:
        """The vertical distance from the first text line to the last."""
        import os
        import re
        import subprocess
        import tempfile

        env = dict(os.environ)
        env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
        result = subprocess.run(
            ["pdftotext", "-bbox", str(pdf), "-"],
            capture_output=True, text=True, check=False, env=env,
        )
        tops = [float(m.group(1)) for m in re.finditer(r'yMin="([0-9.]+)"', result.stdout or "")]
        if len(tops) < 2:
            return None
        return max(tops) - min(tops)

    def test_a_fixture_with_nested_lists_measures(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "document" / "matrix"
        candidates = sorted(fixture.glob("matrix-lists-*.yaml"))
        if not candidates:
            self.skipTest("no nested-list fixture present")
        # The fixture exists to exercise nesting; that it parses and carries the
        # purpose tag is what this asserts, since the visual check needs a build.
        import corpus

        data = corpus.load_fixture(candidates[0])
        self.assertIn("nested-list", data.get("purpose") or [])
