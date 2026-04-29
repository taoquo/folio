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


planning = load_module("folio_diagram_semantic_planning", "diagram_semantic_planning.py")


ECS_TEXT = """
The game engine uses an ECS runtime. Input events and scene loading feed a fixed-tick scheduler.
The scheduler advances the ECS world each frame. Systems query entities by component masks,
mutate component stores, and stream resources through a cache. The world owns entity lifetimes
and component registration, while systems do not own persistent state.
"""

AGENT_TEXT = """
Client requests enter an API gateway. The task planner coordinates a model runtime.
Tool runtime reads a memory store and writes observability events in the background.
"""

WORKFLOW_TEXT = """
Requests enter an API gateway and are handed to a workflow orchestrator.
The orchestrator schedules worker steps, persists workflow state in a state store,
and publishes events to an event bus for retries and async continuations.
"""

DATA_PLATFORM_TEXT = """
Source systems publish events to Kafka. A stream processor transforms records and writes them
into a warehouse. Analysts query dashboards through a serving API, while observability tracks
pipeline health in the background.
"""


class DiagramSemanticPlanningTests(TestCase):
    def test_collect_architecture_evidence_scores_specific_roles(self) -> None:
        evidence = planning.collect_architecture_evidence(AGENT_TEXT)

        self.assertGreater(evidence["gateway"]["score"], 0)
        self.assertGreater(evidence["planner"]["score"], 0)
        self.assertGreater(evidence["runtime"]["score"], 0)
        self.assertGreater(evidence["tools"]["score"], 0)
        self.assertEqual(0, evidence["input"]["score"])

    def test_select_architecture_nodes_suppresses_unbacked_candidates(self) -> None:
        evidence = planning.collect_architecture_evidence(DATA_PLATFORM_TEXT)
        nodes = planning.select_architecture_nodes(evidence)
        node_ids = {node["id"] for node in nodes}

        self.assertIn("kafka", node_ids)
        self.assertIn("processor", node_ids)
        self.assertIn("warehouse", node_ids)
        self.assertNotIn("input", node_ids)
        self.assertNotIn("systems", node_ids)

    def test_extract_architecture_semantics_finds_ecs_roles(self) -> None:
        semantics = planning.extract_architecture_semantics(ECS_TEXT)

        self.assertIn("runtime", [layer["id"] for layer in semantics["layers"]])
        node_ids = {node["id"] for node in semantics["nodes"]}
        self.assertIn("world", node_ids)
        self.assertIn("scheduler", node_ids)
        world = next(node for node in semantics["nodes"] if node["id"] == "world")
        self.assertEqual("world", world["role"])
        self.assertTrue(world["state_owner"])

    def test_extract_architecture_semantics_infers_focus_path(self) -> None:
        semantics = planning.extract_architecture_semantics(ECS_TEXT)

        self.assertEqual(["scheduler", "world", "systems"], semantics["focus_path"])
        self.assertEqual("World owns runtime state while systems execute frame work.", semantics["focus_reason"])

    def test_plan_architecture_from_text_returns_diagram_spec(self) -> None:
        spec = planning.plan_architecture_from_text(ECS_TEXT, "ECS Runtime")

        self.assertEqual("architecture", spec.kind)
        self.assertEqual("horizontal-layers", spec.layout)
        self.assertEqual("world", spec.focus)
        self.assertEqual(["scheduler", "world", "systems"], spec.focus_path)
        self.assertIn("query", [edge.flow for edge in spec.edges])

    def test_plan_architecture_from_non_ecs_text_returns_meaningful_spec(self) -> None:
        spec = planning.plan_architecture_from_text(AGENT_TEXT, "Agent Runtime")

        self.assertEqual("architecture", spec.kind)
        self.assertIn(spec.focus, {"planner", "runtime"})
        self.assertTrue(any(node.role == "orchestrator" for node in spec.nodes))
        self.assertTrue(any(edge.flow in {"control", "read", "write"} for edge in spec.edges))
        self.assertFalse(any(node.id == "input" for node in spec.nodes))

    def test_plan_architecture_from_workflow_text_returns_orchestration_path(self) -> None:
        spec = planning.plan_architecture_from_text(WORKFLOW_TEXT, "Workflow Engine")

        self.assertEqual("architecture", spec.kind)
        self.assertIn(spec.focus, {"orchestrator", "planner"})
        self.assertTrue(any(node.role in {"orchestrator", "event-bus", "storage"} for node in spec.nodes))
        self.assertTrue(any(edge.flow in {"control", "event", "write"} for edge in spec.edges))
        self.assertGreaterEqual(len(spec.focus_path), 2)
        self.assertTrue(any(node.id == "event-bus" for node in spec.nodes))
        self.assertFalse(any(node.id == "input" for node in spec.nodes))

    def test_plan_architecture_from_data_platform_text_returns_pipeline_shape(self) -> None:
        spec = planning.plan_architecture_from_text(DATA_PLATFORM_TEXT, "Data Platform")

        self.assertEqual("architecture", spec.kind)
        self.assertTrue(any(node.role in {"event-bus", "executor", "storage", "entry"} for node in spec.nodes))
        self.assertTrue(any(edge.flow in {"stream", "write", "read"} for edge in spec.edges))
        self.assertIn(spec.layout, {"horizontal-layers", "vertical-stack"})
        self.assertFalse(any(node.id == "input" for node in spec.nodes))
        self.assertFalse(any(node.id == "systems" for node in spec.nodes))
