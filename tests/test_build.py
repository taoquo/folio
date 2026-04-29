import builtins
import importlib.util
import sys
from pathlib import Path
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
                    with mock.patch.object(build, "export_png"):
                        with mock.patch.object(build, "export_pdf"):
                            ok = build.build_diagram_artifact("artifact-text-demo")

        self.assertTrue(ok)
        plan_mock.assert_called_once()
        generated_svg.unlink(missing_ok=True)
