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


models = load_module("folio_diagram_models", "diagram_models.py")


class DiagramModelTests(TestCase):
    def test_load_architecture_spec(self) -> None:
        payload = {
            "kind": "architecture",
            "title": "Agent Stack",
            "layout": "horizontal-layers",
            "width": 960,
            "height": 540,
            "focus": "runtime",
            "layers": [{"id": "core", "label": "Core"}],
            "nodes": [
                {"id": "runtime", "kind": "service", "label": "Model Runtime", "layer": "core"}
            ],
            "edges": [],
        }

        spec = models.load_diagram_spec(payload)

        self.assertEqual("architecture", spec.kind)
        self.assertEqual("horizontal-layers", spec.layout)
        self.assertEqual("runtime", spec.focus)

    def test_reject_unknown_architecture_layout(self) -> None:
        payload = {
            "kind": "architecture",
            "title": "Bad Layout",
            "layout": "zig-zag",
            "nodes": [],
            "edges": [],
        }

        with self.assertRaisesRegex(ValueError, "unsupported architecture layout"):
            models.load_diagram_spec(payload)

    def test_load_uml_class_spec(self) -> None:
        payload = {
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

        spec = models.load_diagram_spec(payload)

        self.assertEqual("uml-class", spec.kind)
        self.assertEqual("PageSpec", spec.types[0].name)

    def test_reject_unknown_relationship_kind(self) -> None:
        payload = {
            "kind": "uml-class",
            "title": "Bad UML",
            "layout": "class-grid",
            "types": [{"id": "A", "kind": "class", "name": "A"}],
            "relationships": [{"source": "A", "target": "A", "kind": "dependency"}],
        }

        with self.assertRaisesRegex(ValueError, "unsupported UML relationship kind"):
            models.load_diagram_spec(payload)

    def test_reference_fixtures_load(self) -> None:
        arch = models.load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-demo.json")
        uml = models.load_diagram_spec_file(ROOT / "references" / "fixtures" / "uml-class-demo.json")

        self.assertEqual("architecture", arch.kind)
        self.assertEqual("uml-class", uml.kind)
