import json
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build
from diagram_layout import layout_diagram
from diagram_models import load_diagram_spec_file
from diagram_render_svg import render_diagram_svg
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.hosting import embed_html_figure, verify_hosted_html
from drawing.scene import SceneText
from drawing.validation import DrawingCompilationError
from drawing.validation.quality import _ink_box
from renderers.svg import render_svg


def fixture(kind: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / "v4" / f"{kind}.json").read_text(encoding="utf-8"))


class DrawingNotationV43Tests(TestCase):
    def test_notation_inputs_are_coordinate_free_and_use_stable_semantic_ids(self) -> None:
        expected_prefixes = {
            "sequence": ("participant:", "message:"),
            "uml-class": ("type:", "relationship:"),
            "er-diagram": ("entity:", "relationship:"),
        }
        for kind, prefixes in expected_prefixes.items():
            payload = fixture(kind)
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            encoded = json.dumps(payload, sort_keys=True)
            ids = [item["id"] for item in result.semantic.marks]
            with self.subTest(kind=kind):
                self.assertNotIn('"x"', encoded)
                self.assertNotIn('"y"', encoded)
                self.assertTrue(all(item.startswith(prefixes) for item in ids))
                self.assertEqual(ids, list(result.scene.reading_order))
                self.assertEqual(len(result.plan.relations), result.metrics.edges)

    def test_notation_relationship_ids_survive_label_changes(self) -> None:
        for kind in ("sequence", "uml-class", "er-diagram"):
            left = fixture(kind)
            right = deepcopy(left)
            relation_key = "messages" if kind == "sequence" else "relationships"
            right[relation_key][0]["label"] = right[relation_key][0].get("label", "relation") + " revised"
            left_result = DEFAULT_COMPILER_REGISTRY.compile_payload(left)
            right_result = DEFAULT_COMPILER_REGISTRY.compile_payload(right)
            with self.subTest(kind=kind):
                self.assertEqual(
                    [item for item in left_result.scene.reading_order if item.startswith(("message:", "relationship:"))],
                    [item for item in right_result.scene.reading_order if item.startswith(("message:", "relationship:"))],
                )

    def test_uml_and_er_parallel_edges_fail_closed_instead_of_collapsing(self) -> None:
        for kind in ("uml-class", "er-diagram"):
            payload = fixture(kind)
            duplicate = deepcopy(payload["relationships"][0])
            duplicate["id"] = "parallel"
            payload["relationships"].append(duplicate)
            with self.subTest(kind=kind), self.assertRaises(DrawingCompilationError) as context:
                DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            self.assertIn("parallel directed", str(context.exception))

    def test_relationships_cannot_cross_unrelated_items(self) -> None:
        payload = fixture("uml-class")
        payload["relationships"] = [
            {"id": "skip", "source": "source", "target": "compiler", "kind": "association"},
        ]
        payload["types"] = [
            {"id": "source", "kind": "class", "name": "Source"},
            {"id": "middle", "kind": "class", "name": "Middle"},
            {"id": "compiler", "kind": "class", "name": "Compiler"},
            {"id": "lower-a", "kind": "class", "name": "LowerA"},
            {"id": "lower-b", "kind": "class", "name": "LowerB"},
        ]
        payload.pop("focus", None)
        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("crosses unrelated item", str(context.exception))

    def test_notation_density_fails_closed_before_text_overflows(self) -> None:
        payload = fixture("er-diagram")
        payload["entities"] = []
        for index in range(8):
            fields = [
                {"id": f"f{field}", "name": f"field{field}", "type": "text", "primary_key": field == 0}
                for field in range(8)
            ]
            payload["entities"].append({"id": f"e{index}", "name": f"Entity{index}", "fields": fields})
        payload["relationships"] = [
            {"id": "r", "source": "e0", "target": "e1", "label": "owns", "source_cardinality": "one", "target_cardinality": "many"}
        ]
        payload.pop("focus_entity", None)
        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("content density cannot fit", str(context.exception))

    def test_text_fit_and_malformed_members_keep_specific_diagnostics(self) -> None:
        sequence = fixture("sequence")
        sequence["participants"] = [
            {"id": f"p{index}", "label": f"P{index}", "kind": "system"}
            for index in range(6)
        ]
        sequence["messages"] = [
            {"id": "long", "source": "p0", "target": "p1", "label": "x" * 48, "kind": "sync"}
        ]
        sequence.pop("focus_participant", None)
        with self.assertRaises(DrawingCompilationError) as sequence_error:
            DEFAULT_COMPILER_REGISTRY.compile_payload(sequence)
        self.assertIn("SQ011", {item.code for item in sequence_error.exception.diagnostics})

        uml = fixture("uml-class")
        uml["types"][0]["attributes"] = 3
        with self.assertRaises(DrawingCompilationError) as uml_error:
            DEFAULT_COMPILER_REGISTRY.compile_payload(uml)
        self.assertIn("UC005", {item.code for item in uml_error.exception.diagnostics})
        self.assertNotIn("CP002", {item.code for item in uml_error.exception.diagnostics})

        er = fixture("er-diagram")
        er["entities"][0]["fields"][0]["nullable"] = True
        with self.assertRaises(DrawingCompilationError) as er_error:
            DEFAULT_COMPILER_REGISTRY.compile_payload(er)
        self.assertIn("ER018", {item.code for item in er_error.exception.diagnostics})

    def test_new_uml_contract_rejects_coordinates_but_legacy_facade_still_loads(self) -> None:
        payload = fixture("uml-class")
        payload["types"][0]["x"] = 24
        with self.assertRaises(DrawingCompilationError) as context:
            DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertIn("unknown field", str(context.exception))

        legacy = load_diagram_spec_file(ROOT / "references" / "fixtures" / "uml-class-demo.json")
        layout = layout_diagram(legacy)
        svg = render_diagram_svg(legacy)
        self.assertTrue(layout.boxes)
        self.assertIn("<svg", svg)

    def test_sequence_message_kinds_and_er_cardinalities_are_visible_and_accessible(self) -> None:
        sequence = DEFAULT_COMPILER_REGISTRY.compile_payload(fixture("sequence"))
        sequence_svg = render_svg(sequence.scene)
        self.assertIn('data-folio-id="message:persist"', sequence_svg)
        self.assertIn('data-folio-id="message:stored"', sequence_svg)
        self.assertIn('data-folio-id="message-head:submit"', sequence_svg)
        self.assertIn('data-folio-id="message-head:persist"', sequence_svg)
        self.assertIn('stroke-dasharray="5 4"', sequence_svg)
        message_groups = [item for item in sequence.scene.primitives if item.id.startswith("message:")]
        self.assertTrue(message_groups)
        self.assertTrue(all(
            type(next(child for child in group.children if child.id.startswith("message-head:"))).__name__ == "ScenePolyline"
            for group in message_groups
        ))

        er = DEFAULT_COMPILER_REGISTRY.compile_payload(fixture("er-diagram"))
        er_svg = render_svg(er.scene)
        self.assertIn("1..*", er_svg)
        self.assertIn('data-folio-id="drawing-description"', er_svg)
        self.assertEqual(len(er.scene.reading_order), er_svg.count('role="listitem"'))

    def test_empty_uml_class_has_no_empty_compartment(self) -> None:
        payload = fixture("uml-class")
        payload["types"] = [{"id": "empty", "kind": "class", "name": "Empty"}]
        payload["relationships"] = []
        payload.pop("focus", None)

        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        svg = render_svg(result.scene)

        self.assertNotIn('data-folio-id="item-divider:empty"', svg)
        box = next(item for item in result.scene.primitives if item.id == "type:empty")
        rect = next(child for child in box.children if child.id == "item-box:empty")
        self.assertEqual(64, rect.box.h)

    def test_notation_canvas_profiles_and_geometry_are_shared_contracts(self) -> None:
        expected = {"sequence": (960, 540), "uml-class": (960, 640), "er-diagram": (960, 640)}
        for kind, dimensions in expected.items():
            payload = fixture(kind)
            for profile in ("artifact", "embed", "page-preview"):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile)
                svg = render_svg(result.scene, profile)
                with self.subTest(kind=kind, profile=profile):
                    self.assertEqual(dimensions, (result.scene.width, result.scene.height))
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                    namespace = result.scene and svg.split('data-folio-namespace="', 1)[1].split('"', 1)[0]
                    self.assertIn(
                        f'aria-labelledby="{namespace}--drawing-title {namespace}--drawing-description"',
                        svg,
                    )

    def test_uml_artifact_target_uses_registry_drawing_source(self) -> None:
        config = build.DIAGRAM_ARTIFACT_TARGETS["artifact-uml-class-demo"]
        self.assertEqual("references/fixtures/v4/uml-class.json", config["drawing"])
        self.assertNotIn("spec", config)

    def test_notation_embeds_and_verifies_in_document_host(self) -> None:
        path = ROOT / "references" / "fixtures" / "v4" / "sequence.json"
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(fixture("sequence"))
        host = '<!DOCTYPE html><html><head></head><body><figure data-folio-diagram-slot="main"></figure></body></html>'
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.html", root / "output.html"
            source.write_text(host, encoding="utf-8")
            embed_html_figure(
                result, fixture=path, host_file=source, output_host=output,
                artifact_dir=root / "assets", contract_key="responsive-html", slot="main",
                caption="The compiler persists the artifact before returning completion to the author.",
            )
            manifest = verify_hosted_html(output)[0]
            self.assertEqual("sequence", manifest["kind"])
            self.assertIsNone(manifest["data"])

    def test_notation_route_labels_never_overlap_each_other_or_a_box(self) -> None:
        for directory in ("minimal", "showcase", "v4"):
            for kind in ("uml-class", "er-diagram"):
                path = ROOT / "references" / "fixtures" / directory / f"{kind}.json"
                if not path.exists():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                boxes = [
                    child.box
                    for group in result.scene.primitives
                    for child in getattr(group, "children", ())
                    if getattr(child, "id", "").startswith("item-box:")
                ]
                labels = [
                    _ink_box(child)
                    for group in result.scene.primitives
                    if getattr(group, "id", "").startswith("relationship:")
                    for child in group.children
                    if isinstance(child, SceneText)
                ]
                with self.subTest(fixture=f"{directory}/{kind}"):
                    self.assertFalse([item.code for item in result.diagnostics if item.level == "ERROR"])
                    for index, label in enumerate(labels):
                        for other in labels[index + 1:]:
                            self.assertFalse(_boxes_touch(label, other))
                        for box in boxes:
                            self.assertFalse(_boxes_touch(label, box))


def _boxes_touch(left, right) -> bool:
    horizontal = min(left.x + left.w, right.x + right.w) - max(left.x, right.x)
    vertical = min(left.y + left.h, right.y + right.h) - max(left.y, right.y)
    return horizontal > 0 and vertical > 0
