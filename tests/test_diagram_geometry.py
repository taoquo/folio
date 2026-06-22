import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


geometry = load_module("folio_diagram_geometry", "diagram_geometry.py")


class DiagramGeometryTests(TestCase):
    def test_static_diagram_templates_pass_geometry_validation(self) -> None:
        diagram_paths = sorted((ROOT / "assets" / "diagrams").glob("*.html"))

        issues = []
        for path in diagram_paths:
            issues.extend(geometry.validate_diagram_html(path))

        self.assertEqual([], issues)

    def test_rejects_svg_markers(self) -> None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False)
        path = Path(handle.name)
        handle.close()
        path.write_text(
            '<svg viewBox="0 0 100 100"><marker id="a"></marker><path marker-end="url(#a)" /></svg>',
            encoding="utf-8",
        )
        try:
            self.assertTrue(geometry.validate_diagram_html(path))
        finally:
            path.unlink(missing_ok=True)
