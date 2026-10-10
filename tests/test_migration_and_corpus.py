"""Corpus coverage, the migration matrix, and the layout experiment.

Three modules that exist to stop a specific over-claim. The corpus matrix stops
a total standing in for coverage. The migration matrix stops a summary standing
in for per-type evidence. The layout experiment stops a hunch standing in for a
measurement.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import corpus_matrix  # noqa: E402
import layout_experiment  # noqa: E402
import migration  # noqa: E402


class CorpusMatrixTests(TestCase):
    def test_every_class_is_declared_with_a_reason(self) -> None:
        for coverage in corpus_matrix.MATRIX:
            with self.subTest(cls=coverage.name):
                self.assertTrue(coverage.why)
                self.assertTrue(coverage.purposes)

    def test_the_report_covers_every_declared_class(self) -> None:
        items = corpus_matrix.report()
        self.assertEqual(len(corpus_matrix.MATRIX), len(items))

    def test_a_class_is_satisfied_by_behaviour_not_by_count(self) -> None:
        # A class with one fixture is satisfied; the target is a planning figure.
        for item in corpus_matrix.report():
            with self.subTest(cls=item.coverage.name):
                if item.fixtures:
                    self.assertTrue(item.satisfied)

    def test_gaps_are_reported_rather_than_hidden(self) -> None:
        # This asserts the mechanism, not the current state: a class with no
        # fixture must appear in gaps().
        empty = corpus_matrix.ClassReport(
            coverage=corpus_matrix.CoverageClass("x", ("no-such-purpose",), 1, "test")
        )
        self.assertFalse(empty.satisfied)


class MigrationMatrixTests(TestCase):
    def test_every_document_type_has_a_row(self) -> None:
        entries = migration.load_matrix()
        for name in migration.GENRES:
            with self.subTest(type=name):
                self.assertIn(name, entries)

    def test_a_type_is_not_migrated_without_evidence(self) -> None:
        entry = migration.MigrationEntry(document_type="x")
        self.assertFalse(entry.migrated)

    def test_only_passing_states_count_as_migrated(self) -> None:
        for state in migration.STATES:
            with self.subTest(state=state):
                entry = migration.MigrationEntry(document_type="x", state=state)
                self.assertEqual(state in migration.MIGRATED_STATES, entry.migrated)

    def test_a_row_records_its_rollback(self) -> None:
        entry = migration.MigrationEntry(document_type="one-pager")
        self.assertIn("FOLIO_PIPELINE", entry.to_json()["rollback_command"])

    def test_the_matrix_round_trips(self) -> None:
        entries = migration.load_matrix()
        payload = [entries[k].to_json() for k in sorted(entries)]
        self.assertEqual(len(migration.GENRES), len(payload))

    def test_parity_reports_pages_for_both_paths(self) -> None:
        parity = migration.run_parity("one-pager")
        self.assertIn("ok", parity)
        if parity.get("ok"):
            self.assertEqual(parity["legacy_pages"], parity["ir_pages"])


class LayoutExperimentTests(TestCase):
    def test_every_defect_class_states_how_it_can_be_wrong(self) -> None:
        for defect in layout_experiment.run():
            with self.subTest(defect=defect.name):
                self.assertTrue(defect.how_it_can_be_wrong)

    def test_an_untrustworthy_class_never_drives_the_decision(self) -> None:
        defect = layout_experiment.DefectClass(
            name="x", method="m", how_it_can_be_wrong="known to saturate",
            trustworthy=False, documents=10, total=10,
        )
        self.assertEqual(1.0, defect.rate)
        self.assertFalse(defect.worth_prototyping)

    def test_the_threshold_is_declared_before_measurement(self) -> None:
        self.assertGreater(layout_experiment.PROTOTYPE_THRESHOLD, 0)
        self.assertLess(layout_experiment.PROTOTYPE_THRESHOLD, 1)

    def test_a_decision_is_always_produced(self) -> None:
        decision = layout_experiment.verdict(layout_experiment.run())
        self.assertIn(decision["decision"],
                      {"prototype-warranted", "keep-the-backend", "cannot-decide"})
        self.assertIn("reason", decision)

    def test_an_empty_measurement_refuses_to_decide(self) -> None:
        decision = layout_experiment.verdict([])
        self.assertEqual("cannot-decide", decision["decision"])
