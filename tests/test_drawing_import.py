import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.importers import ImportError_, detect_dialect, load_diagram_source
from drawing.importers.ledger import MAX_FILE_BYTES

IMPORT_DIR = ROOT / "references" / "fixtures" / "import"
MERMAID_CASES = {
    "flowchart.mmd": "flowchart",
    "sequence.mmd": "sequence",
    "state-machine.mmd": "state-machine",
    "er-diagram.mmd": "er-diagram",
    "uml-class.mmd": "uml-class",
}


class DiagramImportTests(TestCase):
    def test_maintained_sources_import_deterministically_and_compile(self) -> None:
        cases = dict(MERMAID_CASES)
        cases["flowchart.drawio"] = "flowchart"
        for name, kind in cases.items():
            with self.subTest(name=name):
                source = IMPORT_DIR / name
                first, first_ledger = load_diagram_source(source)
                second, second_ledger = load_diagram_source(source)
                self.assertEqual(first, second)
                self.assertEqual(first_ledger.to_dict(), second_ledger.to_dict())
                self.assertEqual(first["kind"], kind)
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(first)
                self.assertEqual(result.kind, kind)
                self.assertEqual([item for item in result.diagnostics if item.level == "ERROR"], [])

    def test_ledger_shape_matches_published_schema_keys(self) -> None:
        schema = json.loads((ROOT / "references" / "schemas" / "diagram-import-ledger.schema.json").read_text(encoding="utf-8"))
        _, ledger = load_diagram_source(IMPORT_DIR / "flowchart.mmd")
        record = ledger.to_dict()
        self.assertEqual(sorted(record), sorted(schema["required"]))
        self.assertEqual(record["schema_version"], "1.0")
        self.assertEqual(record["dialect"], "mermaid")
        self.assertGreater(record["fidelity"], 0.0)
        self.assertLessEqual(record["fidelity"], 1.0)
        for bucket in ("preserved", "downgraded", "dropped"):
            for entry in record[bucket]:
                self.assertEqual(sorted(entry), ["detail", "feature"])

    def test_drawio_ledger_records_geometry_drop_and_dashed_downgrade(self) -> None:
        payload, ledger = load_diagram_source(IMPORT_DIR / "flowchart.drawio")
        record = ledger.to_dict()
        self.assertEqual(record["dialect"], "drawio")
        self.assertIn("geometry", [entry["feature"] for entry in record["dropped"]])
        self.assertIn("dashed edge", [entry["feature"] for entry in record["downgraded"]])
        self.assertEqual([edge["kind"] for edge in payload["edges"] if edge["source"] == "fix"], ["exception-flow"])

    def test_mermaid_state_machine_without_exit_is_marked_persistent(self) -> None:
        with TemporaryDirectory() as temp:
            source = Path(temp) / "loop.mmd"
            source.write_text("stateDiagram-v2\n    [*] --> idle\n    idle --> active: go\n    active --> idle: reset\n", encoding="utf-8")
            payload, ledger = load_diagram_source(source)
        self.assertTrue(payload["persistent"])
        self.assertIn("terminal state", [entry["feature"] for entry in ledger.to_dict()["downgraded"]])
        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

    def test_mermaid_er_without_primary_key_promotes_first_field(self) -> None:
        with TemporaryDirectory() as temp:
            source = Path(temp) / "shop.mmd"
            source.write_text(
                "erDiagram\n"
                "    customer {\n        uuid id\n        text name\n    }\n"
                "    order {\n        uuid id\n        uuid customer_id FK\n    }\n"
                "    customer ||--o{ order : places\n",
                encoding="utf-8",
            )
            payload, ledger = load_diagram_source(source)
        self.assertTrue(payload["entities"][0]["fields"][0]["primary_key"])
        self.assertIn("primary key", [entry["feature"] for entry in ledger.to_dict()["downgraded"]])
        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

    def test_suffix_detection_and_explicit_dialect(self) -> None:
        self.assertEqual(detect_dialect("a.mmd"), "mermaid")
        self.assertEqual(detect_dialect("a.mermaid"), "mermaid")
        self.assertEqual(detect_dialect("a.drawio"), "drawio")
        self.assertEqual(detect_dialect("a.xml"), "drawio")
        with self.assertRaises(ImportError_):
            detect_dialect("a.txt")
        with self.assertRaises(ImportError_):
            load_diagram_source(IMPORT_DIR / "flowchart.mmd", dialect="graphviz")

    def test_remote_sources_are_rejected(self) -> None:
        for value in ("https://example.com/a.mmd", "http://example.com/a.mmd", "//example.com/a.mmd"):
            with self.subTest(value=value), self.assertRaises(ImportError_):
                load_diagram_source(value, dialect="mermaid")

    def test_oversized_and_missing_sources_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "absent.mmd"
            with self.assertRaises(ImportError_):
                load_diagram_source(missing)
            large = Path(temp) / "large.mmd"
            large.write_text("flowchart TD\n" + ("    a --> b\n" * 1), encoding="utf-8")
            large.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
            with self.assertRaises(ImportError_):
                load_diagram_source(large)

    def test_unsupported_header_and_node_budget_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.mmd"
            bad.write_text("gitGraph\n    commit\n", encoding="utf-8")
            with self.assertRaises(ImportError_):
                load_diagram_source(bad)
            wide = Path(temp) / "wide.mmd"
            lines = ["flowchart TD"] + [f"    n{index} --> n{index + 1}" for index in range(20)]
            wide.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ImportError_):
                load_diagram_source(wide)

    def test_compressed_and_multipage_drawio_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            compressed = Path(temp) / "compressed.drawio"
            compressed.write_text(
                '<mxfile host="app.diagrams.net"><diagram id="a" name="Page-1">7Vpbc9o4FP41zOw+</diagram></mxfile>',
                encoding="utf-8",
            )
            with self.assertRaises(ImportError_):
                load_diagram_source(compressed)
            multi = Path(temp) / "multi.drawio"
            multi.write_text(
                '<mxfile><diagram id="a" name="A"><mxGraphModel><root /></mxGraphModel></diagram>'
                '<diagram id="b" name="B"><mxGraphModel><root /></mxGraphModel></diagram></mxfile>',
                encoding="utf-8",
            )
            with self.assertRaises(ImportError_):
                load_diagram_source(multi)
            broken = Path(temp) / "broken.drawio"
            broken.write_text("<mxfile><diagram>", encoding="utf-8")
            with self.assertRaises(ImportError_):
                load_diagram_source(broken)
