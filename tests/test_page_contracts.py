"""Page contracts are defined once and consumed by every build path.

`build.py` enforces the contracts as a hard gate and `stabilize.py` reads the
upper bound when solving for overflow. They previously carried independent
copies, so a contract change could land in one path only. These tests pin the
single-source invariant.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import page_contracts
import stabilize

import build


class PageContractSourceTests(TestCase):
    def test_both_consumers_share_the_contract_module(self) -> None:
        # Identity, not equality: an equal copy would still be free to drift.
        self.assertIs(build.HTML_TARGETS, page_contracts.HTML_TARGETS)
        self.assertIs(build.PPTX_TARGETS, page_contracts.PPTX_TARGETS)

    def test_stabilizer_derives_its_table_from_the_contract_module(self) -> None:
        expected = {
            name: (spec.source, spec.max_pages)
            for name, spec in page_contracts.HTML_TARGETS.items()
        }
        self.assertEqual(expected, stabilize.HTML_TARGETS)

    def test_stabilizer_covers_every_html_contract_target(self) -> None:
        # The stabilizer used to omit equity-report and changelog entirely.
        self.assertEqual(
            sorted(page_contracts.HTML_TARGETS),
            sorted(stabilize.HTML_TARGETS),
        )

    def test_source_files_are_not_duplicated_across_targets(self) -> None:
        sources = [spec.source for spec in page_contracts.HTML_TARGETS.values()]
        self.assertEqual(len(sources), len(set(sources)))

    def test_contracts_are_ordered_and_positive(self) -> None:
        for name, spec in {**page_contracts.HTML_TARGETS, **page_contracts.PPTX_TARGETS}.items():
            with self.subTest(target=name):
                self.assertGreaterEqual(spec.min_pages, 1)
                self.assertLessEqual(spec.min_pages, spec.max_pages)

    def test_strict_page_documents_declare_an_exact_count(self) -> None:
        # These types fit on one page by design; a range would silently relax a
        # documented hard requirement.
        for name in ("one-pager", "one-pager-en", "letter", "letter-en"):
            with self.subTest(target=name):
                spec = page_contracts.HTML_TARGETS[name]
                self.assertEqual(spec.min_pages, spec.max_pages)

    def test_the_resume_keeps_a_strict_floor(self) -> None:
        # The resume's ceiling moved when the published example was built from
        # real content. Its floor did not: a resume that fits on one page has
        # lost content, which is the failure the contract exists to catch.
        for name in ("resume", "resume-en"):
            with self.subTest(target=name):
                spec = page_contracts.HTML_TARGETS[name]
                self.assertEqual(2, spec.min_pages)
                self.assertGreaterEqual(spec.max_pages, spec.min_pages)

    def test_stabilizer_max_pages_matches_the_enforced_ceiling(self) -> None:
        # The solver must never aim above the count the hard gate accepts.
        for name, spec in page_contracts.HTML_TARGETS.items():
            with self.subTest(target=name):
                self.assertEqual(spec.max_pages, stabilize.HTML_TARGETS[name][1])


class StabilizerTargetResolutionTests(TestCase):
    def test_all_targets_are_resolvable(self) -> None:
        self.assertEqual(list(stabilize.HTML_TARGETS), stabilize.resolve_targets(["all"]))

    def test_source_filename_aliases_resolve(self) -> None:
        self.assertEqual(["equity-report"], stabilize.resolve_targets(["equity-report.html"]))
        self.assertEqual(["changelog-en"], stabilize.resolve_targets(["changelog-en.html"]))

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            stabilize.resolve_targets(["not-a-target"])
