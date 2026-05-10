import builtins
import contextlib
import io
import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("folio_build", SCRIPTS_DIR / "build.py")
build = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = build
SPEC.loader.exec_module(build)


class BuildScriptTests(TestCase):
    def test_build_import_does_not_emit_weasyprint_warning_for_static_commands(self) -> None:
        sys.modules.pop("diagram_export", None)
        unique_name = "folio_build_static_import"
        sys.modules.pop(unique_name, None)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            spec = importlib.util.spec_from_file_location(unique_name, SCRIPTS_DIR / "build.py")
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

        self.assertEqual("", stderr.getvalue().strip())
        self.assertTrue(hasattr(module, "sync_check"))

    def test_architecture_demo_assets_exist(self) -> None:
        demo_html = ROOT / "assets" / "demos" / "demo-architecture.html"
        demo_png = ROOT / "assets" / "demos" / "demo-architecture.png"
        demo_pdf = ROOT / "assets" / "demos" / "demo-architecture.pdf"

        self.assertTrue(demo_html.exists(), demo_html)
        self.assertTrue(demo_png.exists(), demo_png)
        self.assertTrue(demo_pdf.exists(), demo_pdf)

    def test_workflow_demo_assets_exist(self) -> None:
        demo_html = ROOT / "assets" / "demos" / "demo-workflow-engine.html"
        demo_png = ROOT / "assets" / "demos" / "demo-workflow-engine.png"
        demo_pdf = ROOT / "assets" / "demos" / "demo-workflow-engine.pdf"

        self.assertTrue(demo_html.exists(), demo_html)
        self.assertTrue(demo_png.exists(), demo_png)
        self.assertTrue(demo_pdf.exists(), demo_pdf)

    def test_uml_demo_assets_exist(self) -> None:
        demo_html = ROOT / "assets" / "demos" / "demo-uml-class.html"
        demo_png = ROOT / "assets" / "demos" / "demo-uml-class.png"
        demo_pdf = ROOT / "assets" / "demos" / "demo-uml-class.pdf"

        self.assertTrue(demo_html.exists(), demo_html)
        self.assertTrue(demo_png.exists(), demo_png)
        self.assertTrue(demo_pdf.exists(), demo_pdf)

    def test_verify_target_reports_oserror_from_weasyprint_import(self) -> None:
        original_import = builtins.__import__

        def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "weasyprint":
                raise OSError("cannot load library 'libgobject-2.0-0'")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=failing_import):
            issues = build.verify_target("one-pager", "one-pager.html", 1, 1, build.TEMPLATES)

        self.assertEqual(
            ["dependency load failed: cannot load library 'libgobject-2.0-0'"],
            issues,
        )

    def test_page_count_issue_allows_values_inside_range(self) -> None:
        self.assertIsNone(build.page_count_issue("portfolio", 6, 4, 8))

    def test_page_count_issue_reports_underflow(self) -> None:
        self.assertEqual(
            "page underflow: 3 pages (expected 4-10)",
            build.page_count_issue("slides", 3, 4, 10),
        )

    def test_build_single_accepts_diagram_artifact_target(self) -> None:
        with mock.patch.object(build, "build_diagram_artifact", return_value=True) as artifact_mock:
            with mock.patch.dict(build.DIAGRAM_ARTIFACT_TARGETS, {"artifact-architecture-demo": {}}, clear=True):
                code = build.build_single("artifact-architecture-demo")

        self.assertEqual(0, code)
        artifact_mock.assert_called_once_with("artifact-architecture-demo")

    def test_page_count_issue_allows_single_page_diagram_pdf(self) -> None:
        self.assertIsNone(build.page_count_issue("artifact-architecture-demo", 1, 1, 1))

    def test_diagram_artifact_targets_cover_showcase_gallery(self) -> None:
        expected_showcases = {
            "demo-architecture",
            "demo-workflow-engine",
            "demo-data-platform",
            "demo-uml-class",
        }
        actual_showcases = {
            config["showcase"]["basename"]
            for config in build.DIAGRAM_ARTIFACT_TARGETS.values()
        }

        self.assertEqual(expected_showcases, actual_showcases)

        for doc_name in ("README.md", "README.zh-CN.md", "index.html", "index-zh.html"):
            text = (ROOT / doc_name).read_text(encoding="utf-8")
            for basename in expected_showcases:
                self.assertIn(f"assets/demos/{basename}.pdf", text)

    def test_homepage_catalog_uses_hybrid_document_tool_structure(self) -> None:
        english = (ROOT / "index.html").read_text(encoding="utf-8")
        chinese = (ROOT / "index-zh.html").read_text(encoding="utf-8")

        for text in (english, chinese):
            self.assertIn('class="master-index-shell"', text)
            self.assertIn('class="archive-sidebar"', text)
            self.assertIn('class="archive-main"', text)
            self.assertIn('class="catalog-index"', text)
            self.assertIn('class="specimen-matrix"', text)
            self.assertIn('class="section-rail"', text)
            self.assertNotIn('class="catalog-metadata"', text)
            self.assertNotIn('class="archive-intro"', text)
            anchors = (
                "output-system",
                "principles",
                "usage",
                "color",
                "type",
                "rhythm",
                "modules",
                "artifacts",
                "web-guidance",
                "travel",
                "lookup",
                "anti-patterns",
            )
            for anchor in anchors:
                self.assertIn(f'href="#{anchor}"', text)
                self.assertIn(f'id="{anchor}"', text)
            rail_start = text.index('class="section-rail"')
            rail_end = text.index("</nav>", rail_start)
            rail = text[rail_start:rail_end]
            rail_positions = [rail.index(f'href="#{anchor}"') for anchor in anchors]
            section_positions = [text.index(f'<section id="{anchor}"') for anchor in anchors]
            self.assertEqual(rail_positions, sorted(rail_positions))
            self.assertEqual(section_positions, sorted(section_positions))
            self.assertNotIn('id="components"', text)

        self.assertIn("Output System", english)
        self.assertIn('<a href="#web-guidance"><span>08</span>Web</a>', english)
        self.assertIn("08 · Web Guidance", english)
        self.assertIn("Hybrid / Document Tool", english)
        self.assertIn("Document Classes", english)
        self.assertIn("Specimen Matrix", english)
        self.assertIn("Artifact Records", english)
        self.assertIn("Section rail + numbered rows", english)
        self.assertIn("Browse outputs", english)

        self.assertIn("输出系统", chinese)
        self.assertIn('<a href="#web-guidance"><span>08</span>Web</a>', chinese)
        self.assertIn("08 · Web Guidance", chinese)
        self.assertIn("Hybrid / Document Tool", chinese)
        self.assertIn("文档类型", chinese)
        self.assertIn("样本矩阵", chinese)
        self.assertIn("图形档案", chinese)
        self.assertIn("章节 rail + 编号行", chinese)
        self.assertIn("查看输出", chinese)

    def test_build_diagram_artifact_syncs_showcase_assets(self) -> None:
        fake_spec = SimpleNamespace(title="Workflow Engine")

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            svg_dir = tmp_path / "generated" / "svg"
            png_dir = tmp_path / "generated" / "png"
            pdf_dir = tmp_path / "generated" / "pdf"
            demos_dir = tmp_path / "demos"

            def fake_export_png(_svg_path: Path, out_path: Path) -> None:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"png")

            def fake_export_pdf(_svg_path: Path, out_path: Path, _title: str) -> None:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"pdf")

            config = {
                "text": "references/fixtures/workflow-engine-demo.txt",
                "title": "Workflow Engine",
                "svg": "workflow-engine-demo.svg",
                "png": "workflow-engine-demo.png",
                "pdf": "workflow-engine-demo.pdf",
                "showcase": {
                    "basename": "demo-workflow-engine",
                    "eyebrow": "Architecture Demo",
                    "heading": "Workflow Engine",
                    "alt": "Workflow engine architecture",
                    "caption": "A workflow orchestration case showing gateway ingress, orchestration, worker execution, state persistence, and event-based continuations.",
                },
            }

            with mock.patch.object(build, "GENERATED_DIAGRAM_SVG", svg_dir):
                with mock.patch.object(build, "GENERATED_DIAGRAM_PNG", png_dir):
                    with mock.patch.object(build, "GENERATED_DIAGRAM_PDF", pdf_dir):
                        with mock.patch.object(build, "DEMOS", demos_dir):
                            with mock.patch.dict(build.DIAGRAM_ARTIFACT_TARGETS, {"artifact-demo": config}, clear=False):
                                with mock.patch.object(build, "plan_architecture_from_text", return_value=fake_spec):
                                    with mock.patch.object(build, "render_diagram_svg", return_value="<svg/>"):
                                        with mock.patch.object(build, "_load_diagram_exporters", return_value=(fake_export_pdf, fake_export_png)):
                                                ok = build.build_diagram_artifact("artifact-demo")

            self.assertTrue(ok)
            self.assertEqual(b"png", (demos_dir / "demo-workflow-engine.png").read_bytes())
            self.assertEqual(b"pdf", (demos_dir / "demo-workflow-engine.pdf").read_bytes())
            self.assertTrue((demos_dir / "demo-workflow-engine.html").exists())
            demo_html = (demos_dir / "demo-workflow-engine.html").read_text(encoding="utf-8")
            self.assertIn("../diagrams/generated/png/workflow-engine-demo.png", demo_html)
            self.assertIn("Workflow Engine", demo_html)

    def test_build_diagram_artifact_supports_text_source(self) -> None:
        fake_spec = SimpleNamespace(title="From Text")
        generated_svg = build.GENERATED_DIAGRAM_SVG / "from-text.svg"
        with mock.patch.dict(
            build.DIAGRAM_ARTIFACT_TARGETS,
            {
                "artifact-text-demo": {
                    "text": "references/fixtures/architecture-demo.txt",
                    "title": "From Text",
                    "svg": "from-text.svg",
                    "png": "from-text.png",
                    "pdf": "from-text.pdf",
                }
            },
            clear=False,
        ):
            with mock.patch.object(build, "plan_architecture_from_text", return_value=fake_spec) as plan_mock:
                with mock.patch.object(build, "render_diagram_svg", return_value="<svg/>"):
                    with mock.patch.object(build, "_load_diagram_exporters", return_value=(mock.Mock(), mock.Mock())):
                            ok = build.build_diagram_artifact("artifact-text-demo")

        self.assertTrue(ok)
        plan_mock.assert_called_once()
        generated_svg.unlink(missing_ok=True)
