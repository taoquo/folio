import inspect
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from diagram_models import load_diagram_spec_file
from diagram_semantic_planning import plan_architecture_from_text
from drawing.connectors.postprocess import clean_polyline
from drawing.grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR
from drawing.layout.constraints import compile_layout_constraints
from drawing.models import DrawingOverrides, DrawingPlan
from drawing.pipeline import compile_architecture, compile_drawing_plan, drawing_plan_from_spec
from drawing.planner import plan_drawing
from drawing.semantics.models import SemanticDiagram, SemanticEdge, SemanticNode
from drawing.typography.fit import fit_node_content
from drawing.typography.measure import measure_text
from drawing.validation import collect_metrics, diagnose_taste, validate_drawing_grammar, validate_drawing_semantics, validate_scene_geometry
from renderers import svg as svg_renderer


class DrawingDslTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-demo.json")

    def test_pipeline_exposes_three_readable_intermediate_representations(self) -> None:
        semantic, drawing, _layout, scene = compile_architecture(self.spec)

        self.assertEqual("architecture", drawing.kind)
        self.assertEqual(self.spec.title, semantic.title)
        self.assertEqual(self.spec.width, scene.width)
        self.assertNotIn("x", drawing.to_dict()["nodes"][0])
        self.assertIn("box", scene.to_dict()["nodes"][0])
        json.dumps(semantic.to_dict())
        json.dumps(drawing.to_dict())
        json.dumps(scene.to_dict())

    def test_grammar_is_single_source_for_layout_constraints(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        constraints = compile_layout_constraints(drawing)
        geometry = DEFAULT_ARCHITECTURE_GRAMMAR.geometry

        self.assertEqual((geometry.node_width, geometry.node_height), next(iter(constraints.node_sizes.values())))
        self.assertEqual(geometry.node_gap, constraints.node_gap)
        self.assertEqual(geometry.layer_gap, constraints.layer_gap)
        self.assertEqual(drawing.composition.sidecars, constraints.sidecars)

    def test_drawing_plan_uses_small_semantic_vocabulary(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)

        self.assertIn(drawing.composition.pattern, {"layered", "pipeline", "hub"})
        self.assertTrue({node.archetype for node in drawing.nodes} <= {"component", "datastore", "external", "cloud"})
        self.assertTrue({edge.channel for edge in drawing.edges} <= {"primary-flow", "secondary-flow", "async-flow"})
        serialized = json.dumps(drawing.to_dict())
        self.assertNotIn("#B83D2E", serialized)

    def test_expert_override_changes_intent_without_exposing_pixels(self) -> None:
        semantic, _drawing, _layout, _scene = compile_architecture(self.spec)
        overridden = plan_drawing(semantic, overrides=DrawingOverrides(composition="hub", focus_node="world"))

        self.assertEqual("hub", overridden.composition.pattern)
        self.assertEqual("world", overridden.hierarchy.focus_node)
        self.assertNotIn("x", overridden.to_dict()["nodes"][0])

    def test_handwritten_drawing_plan_round_trips_and_compiles(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        drawing = DrawingPlan.from_dict(payload)
        _layout, scene = compile_drawing_plan(drawing)

        self.assertEqual("2.0", drawing.schema_version)
        self.assertEqual({node["id"] for node in payload["nodes"]}, {node.id for node in drawing.nodes})
        self.assertFalse(validate_drawing_grammar(drawing))
        self.assertFalse(validate_scene_geometry(scene))

    def test_validators_report_actionable_levels_without_a_score(self) -> None:
        _semantic, drawing, _layout, scene = compile_architecture(self.spec)
        diagnostics = [
            *validate_drawing_semantics(drawing),
            *validate_drawing_grammar(drawing),
            *validate_scene_geometry(scene),
            *diagnose_taste(drawing, scene),
        ]

        self.assertFalse(any(item.level == "ERROR" for item in diagnostics))
        self.assertTrue(all(item.level in {"ERROR", "WARNING", "TASTE"} for item in diagnostics))
        self.assertFalse(any("score" in item.message.lower() for item in diagnostics))

    def test_semantic_validator_rejects_unknown_spine_node(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        invalid = replace(drawing, composition=replace(drawing.composition, spine=(*drawing.composition.spine, "missing")))

        diagnostics = validate_drawing_semantics(invalid)

        self.assertTrue(any(item.code == "DG007" for item in diagnostics))

    def test_connector_postprocess_removes_duplicates_and_collinear_points(self) -> None:
        points = clean_polyline([(0, 0), (0, 0), (0, 7), (0, 16), (16, 16)])

        self.assertEqual(((0, 0), (0, 16), (16, 16)), points)

    def test_composition_patterns_produce_distinct_geometry(self) -> None:
        semantic, drawing, _layout, _scene = compile_architecture(self.spec)
        layered_layout, _ = compile_drawing_plan(drawing)
        pipeline_layout, _ = compile_drawing_plan(plan_drawing(semantic, overrides=DrawingOverrides(composition="pipeline")))
        hub_layout, _ = compile_drawing_plan(plan_drawing(semantic, overrides=DrawingOverrides(composition="hub")))

        self.assertNotEqual(layered_layout.boxes, pipeline_layout.boxes)
        self.assertNotEqual(layered_layout.boxes, hub_layout.boxes)
        self.assertNotEqual(pipeline_layout.boxes, hub_layout.boxes)

    def test_spine_order_and_fan_attach_points_affect_layout(self) -> None:
        semantic, drawing, _layout, _scene = compile_architecture(self.spec)
        spine = ("input", "scheduler", "world")
        pipeline = plan_drawing(semantic, overrides=DrawingOverrides(composition="pipeline", spine=spine))
        layout, scene = compile_drawing_plan(pipeline)

        centers = [layout.boxes[node_id].x + layout.boxes[node_id].w // 2 for node_id in spine]
        self.assertEqual(centers, sorted(centers))
        endpoints = [edge.points[0] for edge in scene.edges if edge.source == drawing.hierarchy.focus_node]
        self.assertEqual(len(endpoints), len(set(endpoints)))

    def test_metrics_are_structured_and_regression_friendly(self) -> None:
        semantic, drawing, _layout, scene = compile_architecture(self.spec)
        metrics = collect_metrics(drawing, scene, semantic_node_count=len(semantic.nodes))

        self.assertEqual(len(semantic.nodes), metrics.semantic_nodes)
        self.assertEqual(len(scene.nodes), metrics.visual_nodes)
        self.assertEqual(0, metrics.text_overflow)
        self.assertEqual(0, metrics.crossings)

    def test_information_reduction_actions_are_reviewable(self) -> None:
        semantic = SemanticDiagram(
            title="Reduction",
            nodes=(
                SemanticNode("left", "Left", "external", domain="surface"),
                SemanticNode("right", "Right", "external", domain="surface"),
                SemanticNode("core", "Core", "orchestrator", domain="runtime"),
            ),
            edges=(
                SemanticEdge("e1", "left", "core", "call"),
                SemanticEdge("e2", "right", "core", "call"),
            ),
            groups=(),
            layer_order=("surface", "runtime"),
        )

        drawing = plan_drawing(semantic)
        merge = next(item for item in drawing.reductions if item.action == "merge")
        self.assertEqual(("left", "right"), merge.targets)
        self.assertFalse(merge.applied)

    def test_connector_scene_resolves_rounding_labels_and_crossing_bridges(self) -> None:
        _semantic, _drawing, _layout, scene = compile_architecture(self.spec)
        self.assertTrue(all(edge.corner_radius == 8 for edge in scene.edges))
        self.assertTrue(all(edge.label_box is not None for edge in scene.edges if edge.label))

    def test_typography_measures_cjk_and_degrades_metadata(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        content = replace(drawing.nodes[0].content, title="模型运行时与事件协调中心", metadata="retrieval-memory-store-with-a-long-technical-suffix")
        fitted = fit_node_content(content, 176, 72)

        self.assertGreater(measure_text("模型", 12), measure_text("AI", 12))
        self.assertLessEqual(len(fitted.title), 2)
        self.assertIsNone(fitted.metadata)

    def test_svg_renderer_contains_no_visual_semantic_branching(self) -> None:
        source = inspect.getsource(svg_renderer)

        self.assertNotIn("node.kind", source)
        self.assertNotIn("focus", source)
        self.assertNotIn("importance", source)
        self.assertNotIn("async-flow", source)

    def test_three_stage_snapshots_are_deterministic(self) -> None:
        fixtures = {
            "agent-runtime": ("agent-runtime-demo.txt", "Agent Runtime"),
            "workflow-engine": ("workflow-engine-demo.txt", "Workflow Engine"),
            "data-platform": ("data-platform-demo.txt", "Data Platform"),
        }
        snapshot_dir = ROOT / "references" / "fixtures" / "drawing"
        for name, (filename, title) in fixtures.items():
            text = (ROOT / "references" / "fixtures" / filename).read_text(encoding="utf-8")
            semantic, drawing, _layout, scene = compile_architecture(plan_architecture_from_text(text, title))
            self.assertEqual(json.loads((snapshot_dir / f"{name}.semantic.json").read_text()), json.loads(json.dumps(semantic.to_dict())))
            self.assertEqual(json.loads((snapshot_dir / f"{name}.drawing.json").read_text()), json.loads(json.dumps(drawing.to_dict())))
            self.assertEqual(json.loads((snapshot_dir / f"{name}.scene.json").read_text()), json.loads(json.dumps(scene.to_dict())))

    def test_chinese_architecture_snapshot_uses_same_pipeline(self) -> None:
        snapshot_dir = ROOT / "references" / "fixtures" / "drawing"
        spec = load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-cn-demo.json")
        semantic, drawing, _layout, scene = compile_architecture(spec)

        self.assertEqual(json.loads((snapshot_dir / "architecture-cn.semantic.json").read_text()), json.loads(json.dumps(semantic.to_dict(), ensure_ascii=False)))
        self.assertEqual(json.loads((snapshot_dir / "architecture-cn.drawing.json").read_text()), json.loads(json.dumps(drawing.to_dict(), ensure_ascii=False)))
        self.assertEqual(json.loads((snapshot_dir / "architecture-cn.scene.json").read_text()), json.loads(json.dumps(scene.to_dict(), ensure_ascii=False)))
        self.assertFalse(validate_scene_geometry(scene))

    def test_dense_fixture_stays_within_hard_budget_and_emits_taste_diagnostics(self) -> None:
        dense = load_diagram_spec_file(ROOT / "references" / "fixtures" / "dense-architecture-demo.json")
        _semantic, drawing, _layout, scene = compile_architecture(dense)
        diagnostics = [*validate_drawing_semantics(drawing), *diagnose_taste(drawing, scene)]

        self.assertFalse(any(item.level == "ERROR" for item in diagnostics))
        self.assertTrue(any(item.code == "DG008" for item in diagnostics))
        self.assertTrue(any(item.code == "DG203" for item in diagnostics))
