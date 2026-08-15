import importlib.util
import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("folio_cli", SCRIPTS_DIR / "folio.py")
folio = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = folio
SPEC.loader.exec_module(folio)


class FolioCliTests(TestCase):
    def test_v4_list_diagram_types_is_registry_derived_in_text_and_json(self) -> None:
        text_output = io.StringIO()
        with mock.patch("sys.stdout", text_output):
            self.assertEqual(0, folio.main(["folio.py", "list-diagram-types"]))
        self.assertIn("architecture\tinput 3.0", text_output.getvalue())

        json_output = io.StringIO()
        with mock.patch("sys.stdout", json_output):
            self.assertEqual(0, folio.main(["folio.py", "list-diagram-types", "--format", "json"]))
        records = json.loads(json_output.getvalue())["types"]
        self.assertEqual(len(folio._diagram_type_records()), len(records))
        self.assertEqual(sorted(item["kind"] for item in records), [item["kind"] for item in records])
        self.assertTrue(all(item["profiles"] == ["artifact", "embed", "page-preview"] for item in records))
        self.assertTrue(all(item["formats"] == ["svg", "png", "pdf"] for item in records))

    def test_v4_init_drawing_emits_every_minimal_compiling_fixture(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        with TemporaryDirectory() as temp:
            for kind in DEFAULT_COMPILER_REGISTRY.kinds:
                output = Path(temp) / f"{kind}.json"
                self.assertEqual(0, folio.main([
                    "folio.py", "init-drawing", kind,
                    "--language", "zh-CN", "--output", str(output),
                ]), kind)
                payload = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(kind, payload["kind"])
                self.assertEqual("zh-CN", payload["language"])
                self.assertEqual(kind, DEFAULT_COMPILER_REGISTRY.compile_payload(payload).kind)

        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(0, folio.main(["folio.py", "init-drawing", "tree"]))
        self.assertEqual("tree", json.loads(stdout.getvalue())["kind"])

    def test_v42_import_chart_data_emits_compiler_ready_json(self) -> None:
        config = ROOT / "references" / "fixtures" / "tabular" / "bar-import.json"
        with TemporaryDirectory() as temp:
            output = Path(temp) / "bar.json"
            self.assertEqual(0, folio.main([
                "folio.py", "import-chart-data", str(config), "--output", str(output),
            ]))
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("bar-chart", payload["kind"])
            self.assertEqual("stacked", payload["mode"])

        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(0, folio.main(["folio.py", "import-chart-data", str(config)]))
        self.assertEqual("bar-chart", json.loads(stdout.getvalue())["kind"])

    def test_v5_import_diagram_emits_payload_and_fidelity_ledger(self) -> None:
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        source = ROOT / "references" / "fixtures" / "import" / "flowchart.mmd"
        with TemporaryDirectory() as temp:
            payload_path = Path(temp) / "flow.json"
            ledger_path = Path(temp) / "flow-ledger.json"
            self.assertEqual(0, folio.main([
                "folio.py", "import-diagram", str(source),
                "--output", str(payload_path), "--ledger-output", str(ledger_path),
            ]))
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual("flowchart", payload["kind"])
            self.assertEqual("flowchart", DEFAULT_COMPILER_REGISTRY.compile_payload(payload).kind)
            self.assertEqual("mermaid", ledger["dialect"])
            self.assertEqual("1.0", ledger["schema_version"])

            drawio_payload = Path(temp) / "gate.json"
            self.assertEqual(0, folio.main([
                "folio.py", "import-diagram",
                str(ROOT / "references" / "fixtures" / "import" / "flowchart.drawio"),
                "--dialect", "drawio", "--output", str(drawio_payload),
            ]))
            self.assertEqual("flowchart", json.loads(drawio_payload.read_text(encoding="utf-8"))["kind"])

    def test_v4_validate_drawing_json_has_stable_diagnostic_envelope(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "minimal" / "bar-chart.json"
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(0, folio.main([
                "folio.py", "validate-drawing", str(fixture), "--format", "json",
            ]))
        valid = json.loads(stdout.getvalue())
        self.assertEqual("valid", valid["status"])
        self.assertEqual("bar-chart", valid["kind"])

        with TemporaryDirectory() as temp:
            invalid_path = Path(temp) / "invalid.json"
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            payload["series"][0]["values"] = []
            invalid_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                self.assertEqual(1, folio.main([
                    "folio.py", "validate-drawing", str(invalid_path), "--format", "json",
                ]))
        invalid = json.loads(stdout.getvalue())
        self.assertEqual("invalid", invalid["status"])
        self.assertTrue(invalid["diagnostics"])
        self.assertEqual(
            {"code", "severity", "stage", "kind", "path", "message", "hint", "related_ids"},
            set(invalid["diagnostics"][0]),
        )
        self.assertNotIn(temp, json.dumps(invalid))

        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(0, folio.main(["folio.py", "validate-drawing", str(fixture)]))
        self.assertIn("OK: bar-chart drawing is valid", stdout.getvalue())

    def test_v4_batch_render_is_deterministic_collision_safe_and_fail_closed(self) -> None:
        valid = ROOT / "references" / "fixtures" / "minimal" / "tree.json"
        with TemporaryDirectory() as temp:
            source_root = Path(temp) / "inputs"
            output_root = Path(temp) / "output"
            (source_root / "a").mkdir(parents=True)
            (source_root / "b").mkdir(parents=True)
            content = valid.read_text(encoding="utf-8")
            (source_root / "a" / "same.json").write_text(content, encoding="utf-8")
            (source_root / "b" / "same.json").write_text(content, encoding="utf-8")
            invalid = json.loads(content)
            invalid["nodes"] = []
            (source_root / "z-invalid.json").write_text(json.dumps(invalid), encoding="utf-8")
            stale_name = folio._batch_output_name("z-invalid.json", "svg")
            output_root.mkdir(parents=True)
            (output_root / stale_name).write_text("stale", encoding="utf-8")

            reports = []
            for _ in range(2):
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    self.assertEqual(1, folio.main([
                        "folio.py", "batch-render-drawings", str(source_root),
                        "--output-dir", str(output_root), "--report-format", "json",
                    ]))
                reports.append(json.loads(stdout.getvalue()))

            self.assertEqual(reports[0], reports[1])
            self.assertEqual(["a/same.json", "b/same.json", "z-invalid.json"], [item["input"] for item in reports[0]["items"]])
            rendered = [item["output"] for item in reports[0]["items"] if item["status"] == "rendered"]
            self.assertEqual(2, len(set(rendered)))
            self.assertTrue(all((output_root / name).exists() for name in rendered))
            self.assertIsNone(reports[0]["items"][-1]["output"])
            self.assertFalse((output_root / stale_name).exists())

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                self.assertEqual(1, folio.main([
                    "folio.py", "batch-render-drawings", str(source_root),
                    "--output-dir", str(output_root), "--fail-fast",
                ]))
            self.assertIn("ERROR:", stdout.getvalue())

    def test_v4_render_dependency_failure_uses_exit_code_two_without_partial_output(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "minimal" / "tree.json"
        with TemporaryDirectory() as temp:
            output = Path(temp) / "tree.png"
            with mock.patch.object(folio, "_render_compilation", side_effect=folio.DrawingDependencyError()):
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    code = folio.main([
                        "folio.py", "render-drawing", str(fixture),
                        "--format", "png", "--output", str(output),
                    ])
        self.assertEqual(2, code)
        self.assertFalse(output.exists())
        self.assertIn("dependency", stdout.getvalue())

    def test_v41_list_embed_and_verify_html_host_workflow(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(0, folio.main(["folio.py", "list-drawing-hosts", "--format", "json"]))
        hosts = json.loads(stdout.getvalue())["hosts"]
        self.assertEqual(4, len(hosts))

        fixture = ROOT / "references" / "fixtures" / "minimal" / "bar-chart.json"
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source.html"
            output = Path(temp) / "output.html"
            source.write_text(
                '<!DOCTYPE html><html><head></head><body>'
                '<figure data-folio-diagram-slot="chart"></figure>'
                '</body></html>',
                encoding="utf-8",
            )
            self.assertEqual(0, folio.main([
                "folio.py", "embed-drawing", str(fixture),
                "--host-contract", "responsive-html",
                "--host-file", str(source), "--output-host", str(output),
                "--slot", "chart",
                "--caption", "The first category establishes the exact baseline for future comparisons.",
            ]))
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                self.assertEqual(0, folio.main([
                    "folio.py", "verify-drawing-host", str(output), "--format", "json",
                ]))

        report = json.loads(stdout.getvalue())
        self.assertEqual("valid", report["status"])
        self.assertEqual("bar-chart", report["diagrams"][0]["kind"])

    def test_list_targets_prints_all_target_groups(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "list-targets"])

        text = stdout.getvalue()
        self.assertEqual(0, code)
        self.assertIn("HTML targets:", text)
        self.assertIn("one-pager", text)
        self.assertIn("Diagram targets:", text)
        self.assertIn("diagram-architecture", text)
        self.assertIn("Artifact targets:", text)
        self.assertIn("artifact-architecture-demo", text)
        self.assertIn("Slide targets:", text)
        self.assertIn("slides-en", text)

    def test_package_delegates_to_package_script(self) -> None:
        with mock.patch.object(folio.subprocess, "run") as run_mock:
            run_mock.return_value.returncode = 0
            code = folio.main(["folio.py", "package"])

        self.assertEqual(0, code)
        command = run_mock.call_args[0][0]
        self.assertEqual(["bash", str(ROOT / "scripts" / "package-skill.sh")], command)
        self.assertEqual(ROOT, run_mock.call_args.kwargs["cwd"])

    def test_diagram_catalog_forwards_visual_baseline_options(self) -> None:
        with mock.patch("diagram_catalog.main", return_value=0) as catalog_main:
            code = folio.main([
                "folio.py",
                "diagram-catalog",
                "--output-dir", "/tmp/catalog",
                "--baseline", "references/fixtures/drawing/catalog-baseline-v3.json",
                "--baseline-report", "/tmp/catalog-report.json",
            ])

        self.assertEqual(0, code)
        forwarded = catalog_main.call_args.args[0]
        self.assertIn("--baseline", forwarded)
        self.assertIn("references/fixtures/drawing/catalog-baseline-v3.json", forwarded)
        self.assertIn("--baseline-report", forwarded)

    def test_verify_delegates_to_build_script_with_target(self) -> None:
        with mock.patch.object(folio.subprocess, "run") as run_mock:
            run_mock.return_value.returncode = 0
            code = folio.main(["folio.py", "verify", "resume-en"])

        self.assertEqual(0, code)
        command = run_mock.call_args[0][0]
        self.assertEqual([sys.executable, str(ROOT / "scripts" / "build.py"), "--verify", "resume-en"], command)

    def test_draw_plan_emits_reviewable_json(self) -> None:
        stdout = io.StringIO()
        fixture = ROOT / "references" / "fixtures" / "architecture-demo.json"
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "draw-plan", str(fixture), "--explain-drawing"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("architecture", payload["kind"])
        self.assertIn("explanation", payload)

    def test_compile_commands_accept_output_profile(self) -> None:
        stdout = io.StringIO()
        fixture = ROOT / "references" / "fixtures" / "flowchart" / "linear.json"
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "draw-scene", str(fixture), "--profile", "embed"])

        self.assertEqual(0, code)
        self.assertTrue(json.loads(stdout.getvalue())["description"].startswith("Flowchart:"))

    def test_check_drawing_accepts_architecture_fixture(self) -> None:
        stdout = io.StringIO()
        fixture = ROOT / "references" / "fixtures" / "architecture-demo.json"
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "check-drawing", str(fixture)])

        self.assertEqual(0, code)
        self.assertNotIn("ERROR", stdout.getvalue())

    def test_draw_scene_accepts_handwritten_drawing_plan(self) -> None:
        stdout = io.StringIO()
        fixture = ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json"
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "draw-scene", str(fixture)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, code)
        self.assertEqual(960, payload["width"])
        self.assertTrue(payload["nodes"])

    def test_draw_metrics_emits_regression_counters(self) -> None:
        stdout = io.StringIO()
        fixture = ROOT / "references" / "fixtures" / "architecture-demo.json"
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "draw-metrics", str(fixture)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, code)
        self.assertEqual(0, payload["crossings"])
        self.assertIn("spine_bends", payload)

    def test_aud_001_render_drawing_fails_closed_without_output(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "linear.json").read_text())
        payload.pop("schema_version")
        with TemporaryDirectory() as temp:
            fixture = Path(temp) / "invalid.json"
            output = Path(temp) / "invalid.svg"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                code = folio.main(["folio.py", "render-drawing", str(fixture), "--output", str(output)])
            self.assertEqual(1, code)
            self.assertFalse(output.exists())
            self.assertIn("ERROR", stdout.getvalue())

    def test_render_drawing_propagates_embed_profile(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "flowchart" / "linear.json"
        with TemporaryDirectory() as temp:
            output = Path(temp) / "drawing.svg"

            code = folio.main([
                "folio.py", "render-drawing", str(fixture),
                "--profile", "embed", "--output", str(output),
            ])

            self.assertEqual(0, code)
            self.assertIn('width="100%"', output.read_text(encoding="utf-8"))

    def test_v3_legacy_schema_migration_and_bundle_commands_remain_compatible(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json"
        with TemporaryDirectory() as temp:
            migrated = Path(temp) / "migrated.json"
            bundled = Path(temp) / "bundle.json"

            self.assertEqual(0, folio.main(["folio.py", "migrate-drawing", str(fixture), "--output", str(migrated)]))
            self.assertEqual("2.0", json.loads(migrated.read_text(encoding="utf-8"))["schema_version"])

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                self.assertEqual(0, folio.main(["folio.py", "validate-drawing-schema", str(migrated)]))
            self.assertIn("schema version 2.0", stdout.getvalue())

            self.assertEqual(0, folio.main(["folio.py", "bundle-drawing", str(migrated), "--output", str(bundled)]))
            bundle = json.loads(bundled.read_text(encoding="utf-8"))
            self.assertEqual("architecture", bundle["overview"]["kind"])
            self.assertTrue(bundle["details"])
            self.assertTrue(bundle["navigation"])

    def test_review_drawing_remains_a_compilation_result_adapter(self) -> None:
        fixture = ROOT / "references" / "fixtures" / "flowchart" / "linear.json"
        with TemporaryDirectory() as temp:
            with mock.patch("drawing.review.write_review_bundle", return_value={}) as writer:
                code = folio.main([
                    "folio.py", "review-drawing", str(fixture),
                    "--profile", "page-preview", "--output-dir", temp,
                ])

        self.assertEqual(0, code)
        kwargs = writer.call_args.kwargs
        self.assertEqual("page-preview", kwargs["profile"])
        self.assertIsNotNone(kwargs["compilation_metadata"])
        self.assertTrue(kwargs["normalized_input"])
