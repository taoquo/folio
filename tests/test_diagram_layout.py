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


models = load_module("folio_diagram_models_layout", "diagram_models.py")
layout = load_module("folio_diagram_layout", "diagram_layout.py")
planning = load_module("folio_diagram_semantic_planning_layout", "diagram_semantic_planning.py")


class DiagramLayoutTests(TestCase):
    def test_elk_adapter_lays_out_architecture_fixture(self) -> None:
        spec = models.load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-demo.json")

        result = layout.layout_diagram(spec)

        self.assertTrue(result.boxes)
        self.assertTrue(result.edges)
        self.assertEqual([], layout.validate_layout(result, spec.width, spec.height))

    def test_uml_layout_has_no_node_overlap_and_terminates_edges(self) -> None:
        spec = models.load_diagram_spec_file(ROOT / "references" / "fixtures" / "uml-class-demo.json")

        result = layout.layout_diagram(spec)

        self.assertEqual([], layout.validate_layout(result, spec.width, spec.height))
        for edge in result.edges:
            self.assertIn(edge.target, result.boxes)
            self.assertTrue(layout._point_touches_box(edge.points[-1], result.boxes[edge.target]))

    def test_layout_coordinates_snap_to_four_px_grid(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Grid",
                "layout": "horizontal-layers",
                "nodes": [
                    {"id": "a", "kind": "external", "label": "A"},
                    {"id": "b", "kind": "service", "label": "B"},
                ],
                "edges": [{"source": "a", "target": "b", "kind": "primary", "label": "call"}],
            }
        )

        result = layout.layout_diagram(spec)

        values = []
        for box in result.boxes.values():
            values.extend([box.x, box.y, box.w, box.h])
        for edge in result.edges:
            for point in edge.points:
                values.extend(point)
        self.assertTrue(all(value % 4 == 0 for value in values))

    def test_content_is_centered_within_canvas(self) -> None:
        spec = models.load_diagram_spec(
            {
                "kind": "architecture",
                "title": "Centered",
                "layout": "horizontal-layers",
                "nodes": [
                    {"id": "a", "kind": "external", "label": "A"},
                    {"id": "b", "kind": "service", "label": "B"},
                    {"id": "c", "kind": "store", "label": "C"},
                ],
                "edges": [
                    {"source": "a", "target": "b", "kind": "primary"},
                    {"source": "b", "target": "c", "kind": "primary"},
                ],
            }
        )

        result = layout.layout_diagram(spec)

        stage_center_x = (72 + spec.width - 72) // 2
        center_x = result.bounds.x + result.bounds.w // 2
        self.assertLessEqual(abs(center_x - stage_center_x), 8)

    def test_text_planned_data_platform_routes_without_crossing_nodes(self) -> None:
        text = (ROOT / "references" / "fixtures" / "data-platform-demo.txt").read_text(encoding="utf-8")
        spec = planning.plan_architecture_from_text(text, "Data Platform")

        result = layout.layout_diagram(spec)

        self.assertEqual([], layout.validate_layout(result, spec.width, spec.height))
