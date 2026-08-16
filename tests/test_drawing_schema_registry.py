import json
from copy import deepcopy
import sys
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.schema_registry import list_schema_contracts, schema_contract


class DrawingSchemaRegistryTests(TestCase):
    def test_schema_registry_matches_compiler_registry(self) -> None:
        contracts = list_schema_contracts()

        self.assertEqual(DEFAULT_COMPILER_REGISTRY.kinds, tuple(item.kind for item in contracts))

    def test_every_contract_has_a_parseable_schema_and_compiling_fixture(self) -> None:
        for contract in list_schema_contracts():
            with self.subTest(kind=contract.kind):
                schema = contract.load_schema()
                payload = contract.load_canonical_payload()

                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertTrue(schema["$id"].endswith(f"/{contract.kind}.schema.json"))
                self.assertEqual(contract.kind, payload["kind"])
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertEqual(contract.kind, result.kind)

                minimal = contract.load_minimal_payload()
                self.assertEqual(contract.kind, minimal["kind"])
                minimal_result = DEFAULT_COMPILER_REGISTRY.compile_payload(minimal)
                self.assertEqual(contract.kind, minimal_result.kind)

    def test_schema_contract_metadata_is_portable(self) -> None:
        metadata = schema_contract("waterfall").to_dict()

        self.assertEqual("waterfall", metadata["kind"])
        self.assertFalse(Path(metadata["schema"]).is_absolute())
        self.assertFalse(Path(metadata["canonical_fixture"]).is_absolute())
        self.assertFalse(Path(metadata["minimal_fixture"]).is_absolute())

    def test_all_schema_files_are_stable_json(self) -> None:
        for contract in list_schema_contracts():
            source = contract.schema_path.read_text(encoding="utf-8")
            parsed = json.loads(source)
            self.assertEqual(parsed, json.loads(json.dumps(parsed, ensure_ascii=False)))

    def test_detailed_v4_schemas_match_canonical_and_negative_shapes(self) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is installed by requirements-ci.txt")

        collection_by_kind = {
            "architecture": "nodes",
            "flowchart": "nodes",
            "state-machine": "states",
            "swimlane": "steps",
            "tree": "nodes",
            "layer-stack": "layers",
            "timeline": "events",
            "quadrant": "items",
            "venn": "sets",
            "pyramid": "levels",
            "org-chart": "units",
            "loop-flywheel": "stages",
            "bar-chart": "series",
            "line-chart": "series",
            "donut-chart": "segments",
            "candlestick": "periods",
            "waterfall": "contributions",
            "scatter": "points",
            "gantt": "tasks",
            "heatmap": "rows",
            "sequence": "participants",
            "uml-class": "types",
            "er-diagram": "entities",
        }
        for kind, collection in collection_by_kind.items():
            with self.subTest(kind=kind):
                contract = schema_contract(kind)
                schema = contract.load_schema()
                payload = contract.load_canonical_payload()
                validator = Draft202012Validator(schema)

                self.assertEqual([], list(validator.iter_errors(payload)))
                self.assertEqual([], list(validator.iter_errors(contract.load_minimal_payload())))

                unknown = deepcopy(payload)
                unknown[collection][0]["x"] = 24
                self.assertTrue(list(validator.iter_errors(unknown)))

                missing = deepcopy(payload)
                missing[collection][0].pop("id")
                self.assertTrue(list(validator.iter_errors(missing)))

    def test_authoring_migration_is_idempotent_and_versions_are_registry_aligned(self) -> None:
        from drawing.migrations import LATEST_INPUT_VERSIONS, migrate_authoring_payload

        self.assertEqual(set(DEFAULT_COMPILER_REGISTRY.kinds), set(LATEST_INPUT_VERSIONS))
        for contract in list_schema_contracts():
            payload = contract.load_minimal_payload()
            once = migrate_authoring_payload(payload)
            self.assertEqual(once, migrate_authoring_payload(once))
            self.assertEqual(contract.input_schema_version, once["schema_version"])

        legacy_architecture = schema_contract("architecture").load_minimal_payload()
        legacy_architecture.pop("schema_version")
        migrated = migrate_authoring_payload(legacy_architecture)
        self.assertEqual("3.0", migrated["schema_version"])

    def test_runtime_rejects_unknown_fields_for_every_public_contract(self) -> None:
        from drawing.validation import DrawingCompilationError

        for contract in list_schema_contracts():
            with self.subTest(kind=contract.kind):
                payload = contract.load_minimal_payload()
                payload["pixel_override"] = 1
                with self.assertRaises(DrawingCompilationError) as context:
                    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertTrue(context.exception.diagnostics)
                self.assertTrue(all(item.code for item in context.exception.diagnostics))
