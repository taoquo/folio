"""The connector contract, asserted across every registered kind at once.

These are property tests, not fixture tests: they walk whatever the registry currently holds,
so a diagram type added next month is covered the day it is registered. That is the point. The
bug this file exists to prevent was not a wrong line of code, it was a rule that had to be
restated per family and got missed in one of them; a test that enumerates families defeats
itself the same way.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.connectors.contract import (
    DEFAULT_CONTRACT,
    check_contract,
    collect_connectors,
    node_boxes,
    path_vertices,
)
from drawing.schema_registry import list_schema_contracts, schema_contract


def _fixtures():
    """Every payload the repository publishes, keyed by kind."""
    seen = []
    for directory in ("minimal", "v3", "v4", "v5", "showcase", "flowchart", "drawing"):
        for path in sorted((ROOT / "references" / "fixtures" / directory).glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("kind") in DEFAULT_COMPILER_REGISTRY.kinds:
                seen.append((path, payload))
    for contract in list_schema_contracts():
        payload = contract.load_canonical_payload()
        seen.append((contract.canonical_fixture, payload))
    return seen


class ConnectorContractTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled = []
        for path, payload in _fixtures():
            try:
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            except Exception:  # noqa: BLE001 - a payload that cannot compile is another test's problem
                continue
            cls.compiled.append((path, payload["kind"], result))

    def test_every_registered_kind_is_covered_by_a_fixture(self) -> None:
        """A kind with no compiled fixture would pass every check below by vacuity."""
        covered = {kind for _, kind, _ in self.compiled}
        self.assertEqual(set(DEFAULT_COMPILER_REGISTRY.kinds), covered)

    def test_no_published_fixture_violates_the_connector_contract(self) -> None:
        """The gate runs in _finalize, so this asserts the shipped corpus is actually clean."""
        for path, kind, result in self.compiled:
            findings = check_contract(result.scene)
            with self.subTest(kind=kind, fixture=path.name):
                self.assertEqual([], [f"{item.code}: {item.message}" for item in findings])

    def test_every_arrowhead_has_room_to_read_as_an_arrow(self) -> None:
        """A final run no longer than its arrowhead draws as a kink at the corner."""
        for path, kind, result in self.compiled:
            for connector in collect_connectors(result.scene):
                extent = connector.arrow_extent
                if not extent:
                    continue
                with self.subTest(kind=kind, fixture=path.name, connector=connector.id):
                    self.assertGreater(connector.final_run, extent)

    def test_connectors_stay_inside_the_canvas(self) -> None:
        for path, kind, result in self.compiled:
            scene = result.scene
            for connector in collect_connectors(scene):
                for point in connector.points:
                    with self.subTest(kind=kind, fixture=path.name, connector=connector.id):
                        self.assertTrue(0 <= point[0] <= scene.width)
                        self.assertTrue(0 <= point[1] <= scene.height)

    def test_orthogonal_connectors_stay_orthogonal(self) -> None:
        """Curved families are exempt; a polyline that drifts diagonally is a routing fault."""
        for path, kind, result in self.compiled:
            for connector in collect_connectors(result.scene):
                if connector.curved:
                    continue
                for first, second in connector.segments:
                    with self.subTest(kind=kind, fixture=path.name, connector=connector.id):
                        self.assertTrue(first[0] == second[0] or first[1] == second[1])

    def test_connector_geometry_snaps_to_the_shared_grid(self) -> None:
        for path, kind, result in self.compiled:
            for connector in collect_connectors(result.scene):
                if connector.curved:
                    continue
                for point in connector.points:
                    with self.subTest(kind=kind, fixture=path.name, connector=connector.id):
                        self.assertEqual(0, point[0] % 4)
                        self.assertEqual(0, point[1] % 4)

    def test_node_boxes_are_found_for_every_family(self) -> None:
        """Six kinds emit SceneNode and the rest wrap a shape in a group.

        Reading only ``scene.nodes`` made every node-related check pass by having nothing to
        compare against, which is how a connector running along a node's border stayed invisible.
        """
        for path, kind, result in self.compiled:
            if not collect_connectors(result.scene):
                continue
            with self.subTest(kind=kind, fixture=path.name):
                self.assertNotEqual({}, node_boxes(result.scene))

    def test_arc_path_vertices_skip_radii_and_flags(self) -> None:
        """Pairing every number in a path treats an arc's flags as coordinates."""
        self.assertEqual([(408, 148), (488, 228)], path_vertices("M 408 148 A 168 168 0 0 1 488 228"))
        self.assertEqual(
            [(292, 200), (304, 193), (304, 207)],
            path_vertices("M 292 200 L 304 193 L 304 207 Z"),
        )

    def test_contract_thresholds_match_the_documented_design(self) -> None:
        """references/drawing-architecture.md is the source; drift should fail here first."""
        spec = (ROOT / "references" / "drawing-architecture.md").read_text(encoding="utf-8")
        self.assertIn(f"fan out by at least {DEFAULT_CONTRACT.attach_separation} units", spec)
        self.assertIn(f"{DEFAULT_CONTRACT.elbow_radius}-unit radius", spec)


class ConnectorLayerBoundaryTests(TestCase):
    """Guards that keep the contract from being bypassed as new families arrive."""

    def test_families_do_not_reimplement_the_shared_routing_primitives(self) -> None:
        """Each of these was duplicated per family once; the duplicates are what diverged."""
        shared = {"assign_bridges", "route_is_clear", "blocks_lane", "run_hits_segment", "graze_overlap"}
        contract = ROOT / "scripts" / "drawing" / "connectors" / "contract.py"
        for path in (ROOT / "scripts" / "drawing").rglob("*.py"):
            if path == contract or "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            for name in shared:
                with self.subTest(module=path.name, helper=name):
                    self.assertNotIn(
                        f"def {name}(",
                        source,
                        f"{path.name} redefines {name}; import it from connectors.contract instead",
                    )

    def test_the_contract_gate_is_wired_once_where_every_kind_passes_through(self) -> None:
        """Wiring per family is what let flowcharts ship without a crossing gate."""
        compiler = (ROOT / "scripts" / "drawing" / "compiler.py").read_text(encoding="utf-8")
        self.assertEqual(1, compiler.count("check_contract("), "the gate belongs in _finalize only")
        finalize = compiler.split("def _finalize(", 1)[1]
        self.assertIn("check_contract(", finalize)

    def test_no_module_carries_a_generation_number_in_its_name(self) -> None:
        """v3_common outlived its meaning and hid two unrelated layers behind one name."""
        offenders = []
        for path in (ROOT / "scripts" / "drawing").rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "v3_common.py":
                continue
            if any(part in path.stem for part in ("v1_", "v2_", "v3_", "v4_", "v5_")):
                offenders.append(path.name)
        self.assertEqual([], offenders)

    def test_the_compatibility_shim_only_forwards(self) -> None:
        """v3_common may re-export, never define, so there is one home per symbol."""
        source = (ROOT / "scripts" / "drawing" / "v3_common.py").read_text(encoding="utf-8")
        self.assertNotIn("\ndef ", source)
        self.assertNotIn("\nclass ", source)

    def test_new_kinds_inherit_the_gate_without_extra_wiring(self) -> None:
        """Compiling the canonical payload of every kind must route through check_contract."""
        seen = 0
        for contract in list_schema_contracts():
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(contract.load_canonical_payload())
            codes = {item.code for item in result.diagnostics}
            # DG136/DG204/DG137 are the contract's codes; a clean corpus reports none of them,
            # which only means something because the gate provably ran (see the test above).
            with self.subTest(kind=contract.kind):
                self.assertEqual(set(), codes & {"DG136", "DG204", "DG137"})
            seen += 1
        self.assertEqual(len(DEFAULT_COMPILER_REGISTRY.kinds), seen)

    def test_schema_registry_covers_every_registered_kind(self) -> None:
        """A kind without a contract entry cannot offer --example or be audited by kind."""
        for kind in DEFAULT_COMPILER_REGISTRY.kinds:
            with self.subTest(kind=kind):
                self.assertIsNotNone(schema_contract(kind))
