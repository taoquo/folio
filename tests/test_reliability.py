"""Regression tests at file, subprocess, and rendered-artifact boundaries."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagram_catalog as catalog
import diagram_export as exports
import folio
import stabilize

import build
from drawing.review import _visual_diff

ROOT = Path(__file__).resolve().parents[1]


class BaselineSafetyTests(TestCase):
    def setUp(self):
        from PIL import Image

        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "reference.png"
        Image.new("RGBA", (20, 20), "black").save(self.reference)
        digest = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        record = {
            "kind": "example",
            "png": str(self.reference),
            "profile": "page-preview",
            "registry_key": "example@3",
            "dimensions": {"output": [20, 20]},
            "semantic_ids": ["a"],
            "content_bounds": [2, 2, 18, 18],
            "digests": {"input": "input", "svg": "svg", "png": digest},
        }
        self.manifest = {"coverage": {}, "diagrams": [record]}
        self.baseline = catalog.create_visual_baseline(self.manifest, "Test reference")

    def test_changed_reference_is_rejected_even_when_both_paths_are_identical(self):
        from PIL import Image

        Image.new("RGBA", (20, 20), "red").save(self.reference)
        self.manifest["diagrams"][0]["digests"]["png"] = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        report = catalog.compare_visual_baseline(self.manifest, self.baseline)
        self.assertFalse(report["passed"])
        self.assertTrue(any("baseline PNG digest" in item for item in report["issues"]))

    def test_default_comparison_uses_isolated_outputs(self):
        baseline_file = self.root / "baseline.json"
        baseline_file.write_text(json.dumps(self.baseline))
        original = self.reference.read_bytes()
        seen = {}

        def render(_payload, output, **kwargs):
            seen.update(output=output, **kwargs)
            self.assertNotEqual(catalog.DEFAULT_OUTPUT.resolve(), output.resolve())
            return self.manifest

        with mock.patch.object(catalog, "render_catalog", side_effect=render), redirect_stdout(io.StringIO()):
            with mock.patch.object(catalog, "_run_catalog", wraps=catalog._run_catalog):
                # The real report compares real pixels; only expensive rendering is replaced.
                self.manifest["coverage"] = {"catalog_types": 1, "drawing_dsl": 1, "html_template_baseline": 0}
                self.baseline["coverage"] = dict(self.manifest["coverage"])
                baseline_file.write_text(json.dumps(self.baseline))
                self.assertEqual(0, catalog.main(["--baseline", str(baseline_file)]))
        self.assertEqual(original, self.reference.read_bytes())
        self.assertFalse(seen["output"].parent.exists())
        self.assertNotEqual(catalog.DEFAULT_CONTACT_SHEET, seen["contact_sheet"])

    def test_explicit_reference_output_is_rejected_before_render(self):
        payload = {"diagrams": [{"kind": "example"}]}
        reference = self.root / "catalog" / "png" / "example.png"
        reference.parent.mkdir(parents=True)
        reference.write_bytes(self.reference.read_bytes())
        self.baseline["diagrams"][0]["png"] = str(reference)
        baseline_file = self.root / "baseline.json"
        baseline_file.write_text(json.dumps(self.baseline))
        with (
            mock.patch.object(catalog, "load_catalog", return_value=payload),
            mock.patch.object(catalog, "render_catalog") as render,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                1, catalog.main(["--baseline", str(baseline_file), "--output-dir", str(reference.parent.parent)])
            )
        render.assert_not_called()
        self.assertEqual(self.reference.read_bytes(), reference.read_bytes())

    def test_reference_symlink_cannot_bypass_output_guard(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertTrue(
            catalog._baseline_output_overlap(
                self.baseline, {"diagrams": []}, self.root / "unused", alias / "reference.png", self.root / "sheet.png"
            )
        )

    def test_review_diff_counts_alpha_changes(self):
        from PIL import Image

        transparent = self.root / "transparent.png"
        Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(transparent)
        report = _visual_diff(self.reference, transparent, self.root / "diff.png")
        self.assertEqual(0.25, report["changed_channel_ratio"])


class PdfSafetyTests(TestCase):
    def test_metadata_preserves_outline_destinations_attachments_and_author(self):
        from pypdf import PdfReader, PdfWriter

        with TemporaryDirectory() as temp:
            path = Path(temp) / "report.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            writer.add_outline_item("Chapter One", 0)
            writer.add_named_destination("chapter-one", 0)
            writer.add_attachment("source.txt", b"original source")
            writer.add_metadata({"/Author": "{{AUTHOR}}", "/Title": "Report"})
            writer.write(path)
            build.set_pdf_metadata(path, "Folio Author")
            reader = PdfReader(path)
            self.assertEqual("Chapter One", reader.outline[0].title)
            self.assertIn("chapter-one", reader.named_destinations)
            self.assertEqual([b"original source"], reader.attachments["source.txt"])
            self.assertEqual("Folio Author", reader.metadata.author)
            self.assertEqual("Folio", reader.metadata.producer)
            build.set_pdf_metadata(path, "Another Author")
            self.assertEqual("Folio Author", PdfReader(path).metadata.author)

    def test_failed_metadata_write_preserves_original_bytes(self):
        from pypdf import PdfWriter

        with TemporaryDirectory() as temp:
            path = Path(temp) / "report.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(path)
            before = path.read_bytes()
            with mock.patch.object(PdfWriter, "write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    build.set_pdf_metadata(path)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([path], list(Path(temp).iterdir()))

    def test_fallback_preserves_existing_html_and_cleans_temp_on_success_and_failure(self):
        for returncode in (0, 1):
            with self.subTest(returncode=returncode), TemporaryDirectory() as temp:
                root = Path(temp)
                svg = root / "drawing.svg"
                pdf = root / "drawing.pdf"
                html = root / "drawing.html"
                svg.write_text('<svg viewBox="0 0 960 540"/>')
                html.write_text("original document")
                temp_files = []

                def run(command, temp_files=temp_files, html=html, returncode=returncode, **kwargs):
                    temp_files.append(Path(command[3]))
                    self.assertNotEqual(html, temp_files[-1])
                    self.assertTrue(temp_files[-1].is_file())
                    return subprocess.CompletedProcess(command, returncode, "", "render failed")

                with (
                    mock.patch.object(exports, "_get_weasyprint_html", return_value=None),
                    mock.patch.object(exports.Path, "exists", return_value=True),
                    mock.patch.object(exports.subprocess, "run", side_effect=run),
                ):
                    if returncode:
                        with self.assertRaisesRegex(RuntimeError, "render failed"):
                            exports.export_pdf(svg, pdf, "Test")
                    else:
                        exports.export_pdf(svg, pdf, "Test")
                self.assertEqual("original document", html.read_text())
                self.assertFalse(temp_files[0].exists())


class CliBoundaryTests(TestCase):
    def test_import_stdout_is_a_single_json_document(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/folio.py"),
                "import-diagram",
                str(ROOT / "references/fixtures/import/flowchart.mmd"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("flowchart", json.loads(result.stdout)["kind"])
        self.assertEqual("mermaid", json.loads(result.stderr)["dialect"])

    def _batch(self, broken, fail_fast=False):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            output = root / "output"
            bad = inputs / "a-invalid.json"
            if broken == "link":
                bad.symlink_to(root / "missing.json")
            else:
                bad.write_bytes(b"\xff\xfe")
            (inputs / "b-valid.json").write_bytes((ROOT / "references/fixtures/minimal/bar-chart.json").read_bytes())
            report = root / "report.json"
            args = [
                "folio.py",
                "batch-render-drawings",
                str(inputs),
                "--output-dir",
                str(output),
                "--report-format",
                "json",
                "--report-output",
                str(report),
            ]
            if fail_fast:
                args.append("--fail-fast")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = folio.main(args)
            self.assertNotEqual(0, code)
            data = json.loads(report.read_text())
            self.assertEqual(1, data["failed"])
            self.assertEqual(0 if fail_fast else 1, data["rendered"])
            self.assertEqual(1 if fail_fast else 2, data["total"])
            if not fail_fast:
                self.assertTrue((output / data["items"][1]["output"]).is_file())

    def test_unreadable_input_does_not_cancel_batch(self):
        self._batch("link")

    def test_invalid_encoding_does_not_cancel_batch(self):
        self._batch("encoding")

    def test_fail_fast_still_writes_report(self):
        self._batch("link", True)

    def test_failed_output_cleanup_still_writes_batch_report(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            fixture = ROOT / "references/fixtures/minimal/bar-chart.json"
            stale = output / folio._batch_output_name(fixture.name, "svg")
            stale.mkdir()
            with redirect_stdout(io.StringIO()) as stdout:
                code = folio.main(
                    [
                        "folio.py",
                        "batch-render-drawings",
                        str(fixture),
                        "--output-dir",
                        str(output),
                        "--report-format",
                        "json",
                    ]
                )
            report = json.loads(stdout.getvalue())
            self.assertEqual(2, code)
            self.assertEqual(1, report["failed"])
            self.assertTrue(any(item["code"] == "CLI014" for item in report["items"][0]["diagnostics"]))

    def test_errors_identify_command_and_cause_with_optional_traceback(self):
        for debug in (False, True):
            with (
                self.subTest(debug=debug),
                redirect_stdout(io.StringIO()) as out,
                redirect_stderr(io.StringIO()) as err,
            ):
                with mock.patch.object(folio, "_main", side_effect=OSError("disk full")):
                    self.assertEqual(2, folio.main(["folio.py", *(["--debug"] if debug else []), "render-drawing"]))
            self.assertEqual("", out.getvalue())
            self.assertIn("render-drawing", err.getvalue())
            self.assertIn("OSError: disk full", err.getvalue())
            self.assertEqual(debug, "Traceback" in err.getvalue())


class TokenConsistencyTests(TestCase):
    def test_alpha_endpoints_and_midpoint_use_current_design_token(self):
        self.assertEqual("#F6F0EA", stabilize.blend_rgba_on_parchment(0, 0, 0, 0))
        self.assertEqual("#7B7875", stabilize.blend_rgba_on_parchment(0, 0, 0, 0.5))
        self.assertEqual("#000000", stabilize.blend_rgba_on_parchment(0, 0, 0, 1))

    def test_changed_token_drives_compositing(self):
        with TemporaryDirectory() as temp:
            tokens = Path(temp) / "tokens.json"
            tokens.write_text(json.dumps({"--color-surface-page": "#EEDDBB"}))
            with mock.patch.object(stabilize, "TOKENS_FILE", tokens):
                self.assertEqual("#EEDDBB", stabilize.blend_rgba_on_parchment(0, 0, 0, 0))
