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


class DiagramSemanticPlanningTests(TestCase):
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
