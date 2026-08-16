import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.output import (
    OUTPUT_AUDIENCE_NAMES,
    OUTPUT_DETAIL_NAMES,
    OUTPUT_SIZE_NAMES,
    normalize_output_audience,
    normalize_output_detail,
    normalize_output_size,
    size_export_width,
)
from drawing.scene import SceneGroup, SceneText


def _load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _texts(primitives):
    result = []
    for item in primitives:
        if isinstance(item, SceneGroup):
            result.extend(_texts(item.children))
        elif isinstance(item, SceneText):
            result.append(item)
    return result


class OutputKnobNameTests(TestCase):
    def test_knob_name_tuples_are_stable(self):
        self.assertEqual(("compact", "standard", "wide"), OUTPUT_SIZE_NAMES)
        self.assertEqual(("essential", "standard", "full"), OUTPUT_DETAIL_NAMES)
        self.assertEqual(("executive", "general", "practitioner"), OUTPUT_AUDIENCE_NAMES)

    def test_standard_size_keeps_the_1920_export_contract(self):
        self.assertEqual(1280, size_export_width("compact"))
        self.assertEqual(1920, size_export_width("standard"))
        self.assertEqual(2560, size_export_width("wide"))

    def test_unknown_knob_values_raise(self):
        for func in (normalize_output_size, normalize_output_detail, normalize_output_audience):
            with self.assertRaises(ValueError):
                func("huge")

    def test_normalizers_return_known_values(self):
        self.assertEqual("wide", normalize_output_size("wide"))
        self.assertEqual("essential", normalize_output_detail("essential"))
        self.assertEqual("executive", normalize_output_audience("executive"))


class DetailKnobTests(TestCase):
    def test_detail_thins_grid_lines_without_touching_data(self):
        payload = _load("references/fixtures/v3/bar-chart.json")
        counts = {}
        for detail in OUTPUT_DETAIL_NAMES:
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", detail)
            grid = [item for item in result.scene.primitives if getattr(item, "id", "").startswith("grid:")]
            bars = [item for item in result.scene.primitives if getattr(item, "id", "").startswith("bar:")]
            counts[detail] = (len(grid), len(bars))
        self.assertEqual(4, counts["full"][0])
        self.assertEqual(2, counts["standard"][0])
        self.assertEqual(0, counts["essential"][0])
        self.assertEqual({counts["full"][1]}, {value[1] for value in counts.values()})

    def test_essential_detail_drops_annotations_and_syncs_reading_order(self):
        payload = _load("references/fixtures/v4/line-annotated.json")
        full = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full")
        lean = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "essential")
        self.assertTrue(full.scene.annotations)
        self.assertEqual((), lean.scene.annotations)
        dropped = {item.id for item in full.scene.annotations}
        self.assertFalse(dropped & set(lean.scene.reading_order))

    def test_gantt_gridlines_are_thinned_too(self):
        payload = _load("references/fixtures/v5/gantt.json")
        full = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full")
        lean = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "essential")
        self.assertTrue([item for item in full.scene.primitives if getattr(item, "id", "").startswith("gridline:")])
        self.assertFalse([item for item in lean.scene.primitives if getattr(item, "id", "").startswith("gridline:")])


class AudienceKnobTests(TestCase):
    def test_executive_audience_bumps_small_text_only(self):
        payload = _load("references/fixtures/v3/bar-chart.json")
        general = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full", "general")
        executive = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full", "executive")
        self.assertEqual({8, 9}, {item.size for item in _texts(general.scene.primitives)})
        self.assertEqual({9, 10}, {item.size for item in _texts(executive.scene.primitives)})

    def test_practitioner_audience_is_a_passthrough(self):
        payload = _load("references/fixtures/v3/line-chart.json")
        general = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full", "general")
        practitioner = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, "artifact", "folio", "full", "practitioner")
        self.assertEqual(
            [item.size for item in _texts(general.scene.primitives)],
            [item.size for item in _texts(practitioner.scene.primitives)],
        )


class KnobMatrixTests(TestCase):
    def test_every_catalog_type_compiles_clean_under_all_knob_combinations(self):
        catalog = _load("references/fixtures/diagram-catalog.json")
        self.assertEqual(22, len(catalog["diagrams"]))
        for item in catalog["diagrams"]:
            payload = _load(item["source"])
            for detail in OUTPUT_DETAIL_NAMES:
                for audience in OUTPUT_AUDIENCE_NAMES:
                    with self.subTest(kind=item["kind"], detail=detail, audience=audience):
                        result = DEFAULT_COMPILER_REGISTRY.compile_payload(
                            payload, "artifact", "folio", detail, audience
                        )
                        self.assertEqual(detail, result.detail)
                        self.assertEqual(audience, result.audience)
                        self.assertEqual([], [d.code for d in result.diagnostics])
