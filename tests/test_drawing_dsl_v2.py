import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_models import load_diagram_spec_file

from drawing.bundle import bundle_drawing
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.flowchart import (
    _depths,
    compile_flowchart_payload,
    plan_flowchart,
    semantic_from_flowchart_payload,
    validate_flowchart,
)
from drawing.layout.candidates import rank_layout_candidates, select_layout
from drawing.models import AnnotationPlan, DrawingPlan, VisualRegionPlan
from drawing.pipeline import compile_architecture, compile_drawing_plan, drawing_plan_from_spec
from drawing.schema import migrate_v1_payload, validate_plan_payload
from drawing.validation import DrawingCompilationError, validate_canvas, validate_scene_geometry
from renderers.svg import render_svg


class DrawingDslV2Tests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_diagram_spec_file(ROOT / "references" / "fixtures" / "architecture-demo.json")

    def test_v1_payload_migrates_to_strict_v2_contract(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        payload.pop("schema_version", None)
        migrated = migrate_v1_payload(payload)

        self.assertEqual("2.0", migrated["schema_version"])
        self.assertTrue(all("size_tier" in node for node in migrated["nodes"]))
        self.assertFalse(validate_plan_payload(migrated))
        self.assertEqual("2.0", DrawingPlan.from_dict(migrated).schema_version)

    def test_dynamic_size_pictogram_annotation_and_region_resolve(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        first = drawing.nodes[0]
        drawing = replace(
            drawing,
            nodes=(replace(first, size_tier="wide", pictogram="gateway"), *drawing.nodes[1:]),
            regions=(*drawing.regions, VisualRegionPlan("trust", "trust", "Trust boundary", (first.id,), "trust-boundary")),
            annotations=(AnnotationPlan("note-1", first.id, "node", "note", "Entry policy"),),
        )
        layout, scene = compile_drawing_plan(drawing)
        svg = render_svg(scene)

        self.assertEqual(224, layout.boxes[first.id].w)
        self.assertIn("Entry policy", svg)
        self.assertIn('aria-hidden="true"', svg)
        self.assertFalse(any(item.level == "ERROR" for item in validate_scene_geometry(scene)))

    def test_aud_007_008_candidate_selection_is_bounded_and_deterministic(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        candidates = rank_layout_candidates(drawing)
        left = select_layout(drawing)
        right = select_layout(drawing)

        self.assertLessEqual(len(candidates), 8)
        self.assertEqual(left, right)
        self.assertNotIn("spine-reversed", {item.name for item in candidates})

    def test_bundle_preserves_every_node_with_explicit_navigation(self) -> None:
        drawing = drawing_plan_from_spec(self.spec)
        extras = tuple(replace(drawing.nodes[0], id=f"extra-{index}", region=None) for index in range(6))
        expanded = replace(drawing, nodes=(*drawing.nodes, *extras), regions=())
        bundle = bundle_drawing(expanded)

        self.assertLessEqual(len(bundle.overview.nodes), 9)
        self.assertTrue(all(len(detail.nodes) <= 9 for detail in bundle.details))
        self.assertEqual({node.id for node in expanded.nodes}, set(bundle.navigation))

    def test_flowchart_fixtures_compile_render_and_validate(self) -> None:
        for fixture in sorted((ROOT / "references" / "fixtures" / "flowchart").glob("*.json")):
            payload = json.loads(fixture.read_text())
            semantic, plan, _layout, scene = compile_flowchart_payload(payload)
            diagnostics = [*validate_flowchart(semantic, plan), *validate_scene_geometry(scene)]
            svg = render_svg(scene)

            self.assertFalse(any(item.level == "ERROR" for item in diagnostics), fixture.name)
            self.assertIn('data-folio-id="drawing-title"', svg)
            self.assertIn('data-folio-id="drawing-description"', svg)
            self.assertIn('role="img"', svg)

    def test_flowchart_validation_rejects_invalid_decision_and_unreachable_node(self) -> None:
        semantic = semantic_from_flowchart_payload({
            "kind": "flowchart",
            "title": "Invalid",
            "nodes": [
                {"id": "start", "type": "terminal", "label": "Start"},
                {"id": "decision", "type": "decision", "label": "Proceed?"},
                {"id": "orphan", "type": "step", "label": "Orphan"},
            ],
            "edges": [{"source": "start", "target": "decision"}],
        })
        diagnostics = validate_flowchart(semantic, plan_flowchart(semantic))

        self.assertTrue(any(item.code == "FC006" for item in diagnostics))
        self.assertTrue(any(item.code == "FC007" for item in diagnostics))

    def test_accessible_svg_has_stable_reading_order_ids(self) -> None:
        _semantic, _drawing, _layout, scene = compile_architecture(self.spec)
        svg = render_svg(scene)

        namespace = re.search(r'data-folio-namespace="([^"]+)"', svg).group(1)
        self.assertIn(
            f'aria-labelledby="{namespace}--drawing-title {namespace}--drawing-description"',
            svg,
        )
        self.assertIn('data-reading-order=', svg)
        self.assertIn(f'data-folio-id="{scene.nodes[0].id}"', svg)

    def test_svg_namespace_is_deterministic_explicit_and_reference_safe(self) -> None:
        _semantic, _drawing, _layout, scene = compile_architecture(self.spec)

        default_left = render_svg(scene)
        default_right = render_svg(scene)
        first = render_svg(scene, namespace="slot one")
        second = render_svg(scene, namespace="slot two")

        self.assertEqual(default_left, default_right)
        self.assertIn('data-folio-namespace="slot-one"', first)
        self.assertIn('data-folio-namespace="slot-two"', second)
        first_ids = set(re.findall(r'(?<![-\w])id="([^"]+)"', first))
        second_ids = set(re.findall(r'(?<![-\w])id="([^"]+)"', second))
        self.assertFalse(first_ids & second_ids)
        for svg in (first, second):
            ids = set(re.findall(r'(?<![-\w])id="([^"]+)"', svg))
            labelled = re.search(r'aria-labelledby="([^"]+)"', svg).group(1).split()
            self.assertTrue(set(labelled) <= ids)

    def test_svg_namespace_rejects_values_without_safe_characters(self) -> None:
        _semantic, _drawing, _layout, scene = compile_architecture(self.spec)

        with self.assertRaisesRegex(ValueError, "namespace"):
            render_svg(scene, namespace="///")

    def test_connector_labels_keep_visible_clearance_without_masks(self) -> None:
        for fixture in sorted((ROOT / "references" / "fixtures" / "flowchart").glob("*.json")):
            _semantic, _plan, _layout, scene = compile_flowchart_payload(json.loads(fixture.read_text()))
            svg = render_svg(scene)
            with self.subTest(fixture=fixture.name):
                self.assertNotIn("edge-label-mask", svg)
                self.assertFalse([
                    item for item in validate_scene_geometry(scene)
                    if item.code in {"DG132", "DG133", "DG134", "DG135"}
                ])

    def test_compiler_registry_preserves_v2_generator_kinds(self) -> None:
        self.assertTrue({"architecture", "flowchart"}.issubset(DEFAULT_COMPILER_REGISTRY.kinds))

    def test_compilation_result_preserves_output_profile(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "linear.json").read_text())

        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "embed")

        self.assertEqual("embed", result.profile)
        self.assertEqual(payload, result.normalized_input)
        self.assertEqual("flowchart@2", result.metadata.registry_key)
        self.assertEqual(64, len(result.metadata.input_sha256))

    def test_flowchart_compile_requires_schema_and_rejects_unknown_fields(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "linear.json").read_text())
        payload.pop("schema_version")
        payload["unexpected"] = True

        with self.assertRaises(DrawingCompilationError) as context:
            compile_flowchart_payload(payload)

        self.assertEqual("schema", context.exception.stage)

    def test_flowchart_language_matches_the_cross_family_contract(self) -> None:
        base = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "linear.json").read_text())

        for accepted in (None, "zh"):
            payload = dict(base)
            payload["language"] = accepted
            self.assertEqual([], validate_plan_payload(payload))

        for rejected in ("", "   ", 7, True):
            payload = dict(base)
            payload["language"] = rejected
            with self.assertRaises(DrawingCompilationError) as context:
                compile_flowchart_payload(payload)
            self.assertEqual("schema", context.exception.stage)

    def test_aud_003_parallel_flowchart_edges_preserve_routes_and_labels(self) -> None:
        payload = {
            "schema_version": "2.0", "kind": "flowchart", "title": "Parallel",
            "nodes": [
                {"id": "start", "type": "terminal", "label": "Start"},
                {"id": "end", "type": "terminal", "label": "End"},
            ],
            "edges": [
                {"id": "a", "source": "start", "target": "end", "label": "A"},
                {"id": "b", "source": "start", "target": "end", "label": "B"},
            ],
        }

        _semantic, _plan, layout, scene = compile_flowchart_payload(payload)

        self.assertEqual(2, len({tuple(edge.points) for edge in layout.edges}))
        self.assertEqual(2, len({edge.points for edge in scene.edges}))
        self.assertEqual(["A", "B"], [edge.label.text for edge in scene.edges if edge.label])

    def test_flowchart_rejects_invalid_empty_and_unlabelled_decision(self) -> None:
        cases = (
            {"schema_version": "2.0", "kind": "flowchart", "title": "Empty", "nodes": [], "edges": []},
            {
                "schema_version": "2.0", "kind": "flowchart", "title": "Decision",
                "nodes": [
                    {"id": "start", "type": "terminal", "label": "Start"},
                    {"id": "decision", "type": "decision", "label": "Proceed?"},
                    {"id": "a", "type": "terminal", "label": "A"},
                    {"id": "b", "type": "terminal", "label": "B"},
                ],
                "edges": [
                    {"source": "start", "target": "decision"},
                    {"source": "decision", "target": "a", "kind": "conditional-flow"},
                    {"source": "decision", "target": "b", "kind": "conditional-flow"},
                ],
            },
        )
        for payload in cases:
            with self.subTest(payload["title"]), self.assertRaises(DrawingCompilationError):
                compile_flowchart_payload(payload)

    def test_aud_002_dense_flowchart_never_returns_invalid_scene(self) -> None:
        nodes = [
            {"id": "start", "type": "terminal", "label": "Start"},
            {"id": "decision", "type": "decision", "label": "Choose"},
            *({"id": f"branch-{index}", "type": "step", "label": f"Branch {index}"} for index in range(8)),
            {"id": "end", "type": "terminal", "label": "End"},
        ]
        edges = [
            {"id": "start-decision", "source": "start", "target": "decision"},
            *(
                {"id": f"decision-{index}", "source": "decision", "target": f"branch-{index}", "kind": "conditional-flow", "label": str(index)}
                for index in range(8)
            ),
            *({"id": f"end-{index}", "source": f"branch-{index}", "target": "end"} for index in range(8)),
        ]
        payload = {"schema_version": "2.0", "kind": "flowchart", "title": "Dense", "nodes": nodes, "edges": edges}

        try:
            _semantic, _plan, _layout, scene = compile_flowchart_payload(payload)
        except DrawingCompilationError as exc:
            self.assertEqual("scene", exc.stage)
        else:
            errors = [item for item in [*validate_canvas(scene), *validate_scene_geometry(scene)] if item.level == "ERROR"]
            self.assertFalse(errors)

    def test_aud_012_flowchart_reading_order_covers_every_node_once(self) -> None:
        for fixture in sorted((ROOT / "references" / "fixtures" / "flowchart").glob("*.json")):
            _semantic, _plan, _layout, scene = compile_flowchart_payload(json.loads(fixture.read_text()))
            self.assertEqual(len(scene.nodes), len(scene.reading_order), fixture.name)
            self.assertEqual({node.id for node in scene.nodes}, set(scene.reading_order), fixture.name)

    def test_aud_005_flowchart_negative_semantic_matrix_has_stable_diagnostics(self) -> None:
        cases = {
            "terminal-outgoing": ({
                "schema_version": "2.0", "kind": "flowchart", "title": "Terminal",
                "nodes": [
                    {"id": "start", "type": "terminal", "label": "Start"},
                    {"id": "middle", "type": "terminal", "label": "Middle"},
                    {"id": "end", "type": "terminal", "label": "End"},
                ],
                "edges": [
                    {"source": "start", "target": "middle"},
                    {"source": "middle", "target": "end"},
                ],
            }, "FC016"),
            "non-converging": ({
                "schema_version": "2.0", "kind": "flowchart", "title": "Branches",
                "nodes": [
                    {"id": "start", "type": "terminal", "label": "Start"},
                    {"id": "decision", "type": "decision", "label": "Choose"},
                    {"id": "left", "type": "step", "label": "Left"},
                    {"id": "right", "type": "step", "label": "Right"},
                ],
                "edges": [
                    {"source": "start", "target": "decision"},
                    {"source": "decision", "target": "left", "kind": "conditional-flow", "label": "L"},
                    {"source": "decision", "target": "right", "kind": "conditional-flow", "label": "R"},
                ],
            }, "FC015"),
        }
        for name, (payload, code) in cases.items():
            with self.subTest(name=name), self.assertRaises(DrawingCompilationError) as context:
                compile_flowchart_payload(payload)
            self.assertTrue(any(item.code == code for item in context.exception.diagnostics))

    def test_flowchart_schema_stage_reports_specific_diagnostic_codes(self) -> None:
        base = {
            "schema_version": "2.0", "kind": "flowchart", "title": "Codes",
            "nodes": [
                {"id": "start", "type": "terminal", "label": "Start"},
                {"id": "work", "type": "step", "label": "Work"},
                {"id": "end", "type": "terminal", "label": "End"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "work"},
                {"id": "e2", "source": "work", "target": "end"},
            ],
        }

        def mutate(**changes: object) -> dict:
            payload = json.loads(json.dumps(base))
            for path, value in changes.items():
                cursor: object = payload
                keys = path.split("__")
                for key in keys[:-1]:
                    cursor = cursor[int(key)] if key.isdigit() else cursor[key]
                last = keys[-1]
                cursor[int(last) if last.isdigit() else last] = value
            return payload

        cases = {
            "FC009": mutate(axis="sideways"),
            "FC011": mutate(nodes__1__id="start"),
            "FC012": mutate(edges__1__id="e1"),
            "FC003": mutate(edges__1__target="absent"),
            "FC005": mutate(nodes__1__type="teleport"),
            "FC004": mutate(edges__1__kind="teleport"),
            "FC017": mutate(focus="absent"),
            "FC000": mutate(title="   "),
        }
        for code, payload in cases.items():
            with self.subTest(code=code), self.assertRaises(DrawingCompilationError) as context:
                compile_flowchart_payload(payload)
            self.assertEqual("schema", context.exception.stage)
            self.assertIn(code, {item.code for item in context.exception.diagnostics})

    def test_flowchart_loop_layout_is_independent_of_node_id_naming(self) -> None:
        """Depth relaxation must find back edges structurally, not by node-id luck.

        ``_longest_path`` breaks equal-length ties by comparing node-id tuples, so the spine
        used to flip between the loop branch and the exit branch purely on how nodes were
        named. When the spine missed the loop node, the cycle saturated every depth to the
        node-count ceiling and the layout collapsed into a single row.
        """
        template = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "loop.json").read_text())
        original = ["start", "run", "ok", "retry", "end"]
        renamings = (
            original,
            ["a", "b", "c", "d", "e"],
            ["e", "d", "c", "b", "a"],
            ["submit", "review", "gate", "revise", "ship"],
            ["n1", "n2", "n3", "n4", "n5"],
        )
        baseline: dict[int, int] | None = None
        for renaming in renamings:
            mapping = dict(zip(original, renaming))
            payload = json.loads(json.dumps(template))
            for node in payload["nodes"]:
                node["id"] = mapping[node["id"]]
            for edge in payload["edges"]:
                edge["source"] = mapping[edge["source"]]
                edge["target"] = mapping[edge["target"]]
            with self.subTest(renaming=renaming):
                _, plan, _, scene = compile_flowchart_payload(payload)
                depths = _depths(plan)
                # Renaming is an isomorphism, so the shape of the depth histogram is invariant.
                histogram = {depth: 0 for depth in set(depths.values())}
                for depth in depths.values():
                    histogram[depth] += 1
                self.assertEqual({0: 1, 1: 1, 2: 1, 3: 2}, histogram)
                self.assertEqual(len(payload["nodes"]), len(scene.nodes))
                if baseline is None:
                    baseline = histogram
                self.assertEqual(baseline, histogram)

    def test_flowchart_sibling_branches_leave_room_for_their_arrowheads(self) -> None:
        """Two branches off one decision must mirror each other, arrowheads included.

        The fan-out offset used to shift the connector lane as well as the attach point, so on a
        short corridor one sibling's lane landed 8 units above its target -- exactly the height
        of an arrowhead, which then filled the whole stub and read as a kink at the corner.
        """
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "loop.json").read_text())
        _, plan, _, scene = compile_flowchart_payload(payload)
        branches = [edge for edge in scene.edges if edge.source == "ok"]
        self.assertEqual(2, len(branches))
        finals = []
        for edge in branches:
            last, previous = edge.points[-1], edge.points[-2]
            span = abs(last[1] - previous[1]) if last[0] == previous[0] else abs(last[0] - previous[0])
            arrow_height = max(point[1] for point in edge.arrow.points) - min(point[1] for point in edge.arrow.points)
            with self.subTest(edge=edge.id):
                self.assertGreater(span, arrow_height, "final run must be longer than the arrowhead")
            finals.append(span)
        self.assertEqual(finals[0], finals[1], "sibling branches must approach their targets alike")

    def test_flowchart_row_skipping_edge_avoids_the_nodes_between(self) -> None:
        """A long shortcut must not run along an intermediate node's border.

        Rows are evenly spaced, so the midpoint lane of a multi-row jump coincides with the edge
        of the row in between: the connector then merged with that node's outline and read as a
        third branch leaving it. Such edges take an outer channel instead.
        """
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "dense.json").read_text())
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertEqual(0, result.metrics.crossings)
        self.assertNotIn("DG136", {item.code for item in result.diagnostics})
        boxes = {node.id: node.box for node in result.scene.nodes}
        for edge in result.scene.edges:
            for start, end in zip(edge.points, edge.points[1:]):
                for node_id, box in boxes.items():
                    if node_id in {edge.source, edge.target}:
                        continue
                    horizontal = start[1] == end[1]
                    low, high = sorted((start[0], end[0]) if horizontal else (start[1], end[1]))
                    if horizontal and start[1] in {box.y, box.y + box.h}:
                        overlap = min(high, box.x + box.w) - max(low, box.x)
                    elif not horizontal and start[0] in {box.x, box.x + box.w}:
                        overlap = min(high, box.y + box.h) - max(low, box.y)
                    else:
                        continue
                    with self.subTest(edge=edge.id, node=node_id):
                        self.assertLess(overlap, 16, "connector runs along an unrelated node's border")

    def test_flowchart_rejects_duplicate_ids_unknown_focus_and_complex_loops(self) -> None:
        invalid_contract = {
            "schema_version": "2.0", "kind": "flowchart", "title": "Duplicate",
            "focus": "missing",
            "nodes": [
                {"id": "same", "type": "terminal", "label": "Start"},
                {"id": "same", "type": "terminal", "label": "End"},
            ],
            "edges": [],
        }
        with self.assertRaises(DrawingCompilationError) as context:
            compile_flowchart_payload(invalid_contract)
        codes = {item.code for item in context.exception.diagnostics}
        self.assertIn("FC011", codes)
        self.assertIn("FC017", codes)

        loop_payload = {
            "kind": "flowchart", "title": "Loops",
            "nodes": [
                {"id": "start", "type": "terminal", "label": "Start"},
                *({"id": item, "type": "step", "label": item.upper()} for item in ("a", "b", "c", "d")),
            ],
            "edges": [
                {"source": "start", "target": "a"},
                {"source": "a", "target": "b"}, {"source": "b", "target": "a"},
                {"source": "a", "target": "c"}, {"source": "c", "target": "a"},
                {"source": "a", "target": "d"}, {"source": "d", "target": "a"},
            ],
        }
        semantic = semantic_from_flowchart_payload(loop_payload)
        diagnostics = validate_flowchart(semantic, plan_flowchart(semantic))
        self.assertTrue(any(item.code == "FC018" for item in diagnostics))

    def test_aud_006_017_published_schemas_and_runtime_cover_the_same_core_contracts(self) -> None:
        drawing_schema = json.loads((ROOT / "references" / "schemas" / "drawing-plan-v2.schema.json").read_text())
        flow_schema = json.loads((ROOT / "references" / "schemas" / "types" / "flowchart.schema.json").read_text())
        self.assertFalse(drawing_schema["additionalProperties"])
        self.assertFalse(flow_schema["additionalProperties"])
        self.assertIn("composition", drawing_schema["required"])
        self.assertIn("schema_version", flow_schema["required"])

        payload = json.loads((ROOT / "references" / "fixtures" / "drawing" / "agent-runtime.drawing.json").read_text())
        payload["hierarchy"]["focus_path"] = ["gateway", "missing"]
        payload["edges"][0]["direction"] = "backward"
        payload["edges"][0]["route_policy"] = "manual"
        issues = validate_plan_payload(payload)
        self.assertTrue(any("focus_path" in item for item in issues))
        self.assertTrue(any("direction" in item for item in issues))
        self.assertTrue(any("route_policy" in item for item in issues))
