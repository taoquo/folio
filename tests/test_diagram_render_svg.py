import importlib.util
import sys
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


models = load_module("folio_diagram_models_render", "diagram_models.py")
renderer = load_module("folio_diagram_render_svg", "diagram_render_svg.py")


class DiagramRendererTests(TestCase):
    def test_render_architecture_svg_uses_folio_palette(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Agent Stack",
                "layout": "horizontal-layers",
                "focus": "runtime",
                "layers": [{"id": "core", "label": "Core"}],
                "nodes": [
                    {"id": "entry", "kind": "external", "label": "User", "layer": "core"},
                    {"id": "runtime", "kind": "service", "label": "Runtime", "layer": "core"},
                ],
                "edges": [{"source": "entry", "target": "runtime", "kind": "primary", "label": "query"}],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn('viewBox="0 0 960 540"', svg)
        self.assertIn("#F6F0EA", svg)
        self.assertIn("#B83D2E", svg)
        self.assertIn("Agent Stack", svg)
        self.assertIn("Runtime", svg)

    def test_render_architecture_svg_uses_path_arrowheads(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Arrow Strategy",
                "layout": "horizontal-layers",
                "nodes": [
                    {"id": "a", "kind": "external", "label": "A"},
                    {"id": "b", "kind": "service", "label": "B"},
                ],
                "edges": [{"source": "a", "target": "b", "kind": "primary"}],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertNotIn("marker-end", svg)
        self.assertIn("<path", svg)

    def test_render_uml_class_svg_contains_compartments(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "Build Model",
                "layout": "class-grid",
                "types": [
                    {
                        "id": "PageSpec",
                        "kind": "class",
                        "name": "PageSpec",
                        "attributes": ["source: str"],
                        "methods": ["validate() -> None"],
                    }
                ],
                "relationships": [],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn("PageSpec", svg)
        self.assertIn("source: str", svg)
        self.assertIn("validate() -&gt; None", svg)
