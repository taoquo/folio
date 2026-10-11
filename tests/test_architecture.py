"""Structural checks on the engine.

The other tests ask whether a module works. These ask whether the path that
produces a deliverable uses it -- the question that was missing when the IR
engine was built, tested, verified and not on that path.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import architecture  # noqa: E402


class LayeringTests(TestCase):
    """A layer must not name something above it."""

    def test_the_semantic_core_names_no_renderer(self) -> None:
        for target in ("scripts/document_ir/model.py",
                       "scripts/document_ir/validate.py",
                       "scripts/document_ir/bridge.py"):
            with self.subTest(target=target):
                text = architecture._read(target)
                for library in ("weasyprint", "pptx", "reportlab"):
                    self.assertNotIn(f"import {library}", text)

    def test_the_layering_check_covers_the_core(self) -> None:
        covered = set(architecture.LAYERS)
        self.assertIn("scripts/document_ir/model.py", covered)
        self.assertIn("scripts/document_ir/validate.py", covered)

    def test_a_writer_may_speak_its_format(self) -> None:
        # A writer's job is to project the model onto a format, so importing
        # that format's library is the point of the module.
        self.assertNotIn("scripts/document_ir/writers/pptx.py", architecture.LAYERS)


class ReachabilityTests(TestCase):
    """A capability must be called, not merely imported."""

    def test_an_unused_import_does_not_count_as_use(self) -> None:
        text = "import renderers\n\nHTML(string=x).write_pdf(y)\n"
        self.assertFalse(architecture._used(text, "renderers"))

    def test_a_call_counts_as_use(self) -> None:
        text = "import renderers\nrenderers.probe()\n"
        self.assertTrue(architecture._used(text, "renderers"))

    def test_a_from_import_followed_by_a_call_counts(self) -> None:
        text = "from renderers import weasy\nweasy.render(x)\n"
        self.assertTrue(architecture._used(text, "renderers"))

    def test_the_requirement_is_stated_per_path(self) -> None:
        # A module used by one path must not satisfy the requirement for another.
        self.assertIn("scripts/document_build.py", architecture.REQUIRED_CALLS)
        self.assertIn("scripts/build.py", architecture.REQUIRED_CALLS)

    def test_the_content_path_is_required_to_use_the_renderer_boundary(self) -> None:
        required = architecture.REQUIRED_CALLS["scripts/document_build.py"]
        self.assertIn("renderers", required)


class DeclaredDefaultTests(TestCase):
    """A documented switch default must be the one the code uses."""

    def test_the_switch_table_names_every_projection_switch(self) -> None:
        for variable in ("FOLIO_STYLE_PROJECTION", "FOLIO_LAYOUT_POLICY",
                         "FOLIO_BUILD_MANIFEST"):
            with self.subTest(variable=variable):
                self.assertIn(variable, architecture.DECLARED_DEFAULTS)

    def test_the_declared_defaults_match_the_code(self) -> None:
        result = architecture.declared_defaults()
        errors = [f for f in result.findings if f.severity == "error"]
        self.assertEqual([], [f.to_json() for f in errors])

    def test_the_operating_rules_describe_the_switches(self) -> None:
        docs = architecture._read("AGENTS.md")
        for variable in ("FOLIO_STYLE_PROJECTION", "FOLIO_LAYOUT_POLICY"):
            with self.subTest(variable=variable):
                self.assertIn(variable, docs)


class ReportTests(TestCase):
    def test_the_check_runs(self) -> None:
        result = architecture.check()
        self.assertGreater(result.checked, 0)

    def test_a_finding_says_what_is_wrong_and_where(self) -> None:
        result = architecture.check()
        for finding in result.findings:
            with self.subTest(subject=finding.subject):
                self.assertTrue(finding.area)
                self.assertTrue(finding.detail)
                self.assertTrue(finding.subject)

    def test_the_census_is_serialisable(self) -> None:
        import json

        json.dumps(architecture.check().to_json())

    def test_reachability_ranks_every_module(self) -> None:
        rows = architecture.module_reachability()
        self.assertIn("document_ir", rows)
        for counts in rows.values():
            self.assertIn("production", counts)
            self.assertIn("tests", counts)
