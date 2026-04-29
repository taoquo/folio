import importlib.util
import re
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

    def test_render_architecture_svg_orients_cross_layer_arrowhead(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Cross Layer",
                "layout": "horizontal-layers",
                "layers": [{"id": "top", "label": "Top"}, {"id": "bottom", "label": "Bottom"}],
                "nodes": [
                    {"id": "entry", "kind": "external", "label": "Input", "layer": "top"},
                    {"id": "store", "kind": "store", "label": "Store", "layer": "bottom"},
                ],
                "edges": [{"source": "entry", "target": "store", "kind": "secondary", "label": "sync"}],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertRegex(svg, r'M \d+ \d+ L \d+ \d+ L \d+ \d+" fill="none" stroke=')
        self.assertNotIn("M 292 360 L 300 364 L 292 368", svg)

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

    def test_render_uml_class_svg_renders_relationship_layer(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "World Model",
                "layout": "class-grid",
                "focus": "World",
                "types": [
                    {"id": "World", "kind": "class", "name": "World"},
                    {"id": "Entity", "kind": "class", "name": "Entity"},
                    {"id": "ComponentStore", "kind": "class", "name": "ComponentStore<T>"},
                ],
                "relationships": [
                    {"source": "World", "target": "Entity", "kind": "aggregation", "target_multiplicity": "*"},
                    {"source": "World", "target": "ComponentStore", "kind": "composition", "target_multiplicity": "*"},
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn('class="uml-edge"', svg)
        self.assertIn('class="uml-diamond"', svg)
        self.assertIn(">*</text>", svg)
