import builtins
import importlib.util
import sys
from pathlib import Path
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
