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

    def test_render_architecture_svg_uses_semantic_ports_and_route_hints(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Semantic Routing",
                "layout": "horizontal-layers",
                "layers": [{"id": "surface", "label": "Surface"}, {"id": "runtime", "label": "Runtime"}],
                "nodes": [
                    {"id": "gateway", "kind": "external", "label": "Gateway", "layer": "surface"},
                    {"id": "planner", "kind": "service", "label": "Planner", "layer": "runtime"},
                ],
                "edges": [
                    {
                        "source": "gateway",
                        "target": "planner",
                        "kind": "primary",
                        "label": "route",
                        "source_port": "bottom",
                        "target_port": "left",
                        "route_hint": "drop_to_lower_layer",
                    }
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn('class="arch-edge arch-edge--primary"', svg)
        self.assertRegex(svg, r'd="M \d+ \d+(?: L \d+ \d+){2,}"')

    def test_render_architecture_svg_suppresses_edge_labels_to_avoid_collisions(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Label Hierarchy",
                "layout": "horizontal-layers",
                "focus_path": ["gateway", "planner"],
                "layers": [{"id": "runtime", "label": "Runtime"}],
                "nodes": [
                    {"id": "gateway", "kind": "external", "label": "Gateway", "layer": "runtime"},
                    {"id": "planner", "kind": "service", "label": "Planner", "layer": "runtime"},
                    {"id": "runtime", "kind": "service", "label": "Runtime", "layer": "runtime"},
                ],
                "edges": [
                    {"source": "gateway", "target": "planner", "kind": "primary", "priority": "primary", "label": "route"},
                    {"source": "planner", "target": "runtime", "kind": "secondary", "priority": "background", "label": "events"},
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertNotIn('class="arch-edge-label', svg)
        self.assertNotIn('class="arch-edge-label-bg', svg)
        self.assertIn('class="arch-edge arch-edge--primary', svg)
        self.assertIn('class="arch-edge arch-edge--secondary', svg)

    def test_render_architecture_svg_draws_groups_and_legend(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Grouped Runtime",
                "layout": "horizontal-layers",
                "focus": "planner",
                "focus_path": ["gateway", "planner", "runtime"],
                "layers": [{"id": "runtime", "label": "Runtime"}],
                "groups": [
                    {
                        "id": "control-core",
                        "label": "Control Core",
                        "kind": "subsystem",
                        "layer": "runtime",
                        "members": ["planner", "runtime"],
                    }
                ],
                "legend": [
                    {"flow": "control", "label": "Control", "reason": "Control flow advances the main path"},
                    {"flow": "read", "label": "Read", "reason": "Read flow retrieves supporting context"},
                ],
                "nodes": [
                    {"id": "gateway", "kind": "external", "label": "Gateway", "layer": "runtime"},
                    {"id": "planner", "kind": "service", "label": "Planner", "layer": "runtime"},
                    {"id": "runtime", "kind": "service", "label": "Runtime", "layer": "runtime"},
                ],
                "edges": [
                    {"source": "gateway", "target": "planner", "kind": "primary", "flow": "control"},
                    {"source": "planner", "target": "runtime", "kind": "primary", "flow": "control"},
                    {"source": "runtime", "target": "gateway", "kind": "secondary", "flow": "read"},
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn('class="arch-group"', svg)
        self.assertIn("CONTROL CORE", svg)
        self.assertIn('class="arch-legend"', svg)
        self.assertIn("Control", svg)
        self.assertIn("Read", svg)
        self.assertIn('arch-edge--focus', svg)

    def test_render_architecture_svg_keeps_layer_and_group_scaffolding_readable(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Scaffold Tone",
                "layout": "horizontal-layers",
                "layers": [{"id": "runtime", "label": "Runtime"}],
                "groups": [
                    {
                        "id": "core",
                        "label": "Control Core",
                        "kind": "subsystem",
                        "layer": "runtime",
                        "members": ["planner", "runtime"],
                    }
                ],
                "nodes": [
                    {"id": "planner", "kind": "service", "label": "Planner", "layer": "runtime"},
                    {"id": "runtime", "kind": "service", "label": "Runtime", "layer": "runtime"},
                ],
                "edges": [],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertIn('font-size="11"', svg)
        self.assertIn('letter-spacing="0.08em"', svg)
        self.assertIn('fill-opacity="0.28"', svg)
        self.assertIn('stroke-dasharray="5 4"', svg)
        self.assertIn('font-size="8"', svg)

    def test_architecture_legend_metrics_use_horizontal_band(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Legend Band",
                "layout": "horizontal-layers",
                "legend": [
                    {"flow": "control", "label": "Control"},
                    {"flow": "read", "label": "Read"},
                    {"flow": "write", "label": "Write"},
                ],
                "nodes": [],
                "edges": [],
            }
        )

        metrics = renderer._architecture_legend_metrics(spec)

        self.assertGreater(metrics["width"], metrics["height"] * 4)
        self.assertEqual(metrics["x"] + metrics["width"] // 2, spec.width // 2)
        item_rows = {item["y"] for item in metrics["items"]}
        self.assertEqual(len(item_rows), 1)

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

    def test_render_uml_class_svg_routes_edges_orthogonally(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "Orthogonal UML",
                "layout": "class-grid",
                "types": [
                    {"id": "A", "kind": "class", "name": "A"},
                    {"id": "B", "kind": "class", "name": "B"},
                    {"id": "C", "kind": "class", "name": "C"},
                ],
                "relationships": [
                    {"source": "A", "target": "C", "kind": "association", "label": "uses"},
                    {"source": "B", "target": "C", "kind": "inheritance"},
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertRegex(svg, r'class="uml-edge" d="M \d+ \d+(?: L \d+ \d+){3,}"')

    def test_render_uml_class_svg_uses_separate_lanes_for_labels(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "Lane Labels",
                "layout": "class-grid",
                "types": [
                    {"id": "Session", "kind": "class", "name": "Session", "x": 120, "y": 140},
                    {"id": "Store", "kind": "class", "name": "Store", "x": 680, "y": 140},
                    {"id": "Status", "kind": "enum", "name": "Status", "x": 680, "y": 420},
                ],
                "relationships": [
                    {"source": "Session", "target": "Store", "kind": "association", "label": "retrieves"},
                    {"source": "Session", "target": "Status", "kind": "association", "label": "state"},
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertRegex(svg, r'>retrieves</text>')
        self.assertRegex(svg, r'>state</text>')
        self.assertRegex(svg, r'class="uml-edge" d="M \d+ \d+(?: L \d+ \d+){3,}"')

    def test_render_uml_class_svg_uses_elk_route_for_route_policy(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "Route Policy UML",
                "layout": "class-grid",
                "types": [
                    {"id": "Session", "kind": "class", "name": "Session", "x": 120, "y": 140},
                    {"id": "Store", "kind": "class", "name": "Store", "x": 680, "y": 140},
                ],
                "relationships": [
                    {
                        "source": "Session",
                        "target": "Store",
                        "kind": "association",
                        "label": "retrieves",
                        "route_policy": "top-lane",
                    }
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertRegex(svg, r'class="uml-edge" d="M \d+ \d+(?: L \d+ \d+){3,}"')

    def test_render_uml_class_svg_uses_elk_label_placement(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "uml-class",
                "title": "Label Lane UML",
                "layout": "class-grid",
                "types": [
                    {"id": "Session", "kind": "class", "name": "Session", "x": 120, "y": 140},
                    {"id": "Store", "kind": "class", "name": "Store", "x": 680, "y": 140},
                ],
                "relationships": [
                    {
                        "source": "Session",
                        "target": "Store",
                        "kind": "association",
                        "label": "retrieves",
                        "route_policy": "top-lane",
                        "label_lane": "top",
                        "label_offset": -10,
                    }
                ],
            }
        )

        svg = renderer.render_diagram_svg(spec)

        self.assertRegex(svg, r'<text x="\d+" y="\d+" fill="#85776F" font-size="9"[^>]*>retrieves</text>')
        self.assertIn(">retrieves</text>", svg)
