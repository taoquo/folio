import json
import math
import sys
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_catalog import load_catalog
from diagram_export import export_pdf, export_png
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.scene import ScenePolyline
from drawing.validation import DrawingCompilationError
from renderers.svg import render_svg


NEW_KINDS = {
    "state-machine", "swimlane", "tree", "layer-stack", "timeline", "quadrant",
    "venn", "bar-chart", "line-chart", "donut-chart", "candlestick", "waterfall",
    "sequence", "uml-class", "er-diagram",
    "pyramid", "org-chart", "loop-flywheel", "scatter", "gantt", "heatmap",
}
ALL_KINDS = NEW_KINDS | {"architecture", "flowchart"}


def catalog_payloads():
    return {
        item["kind"]: json.loads((ROOT / item["source"]).read_text(encoding="utf-8"))
        for item in load_catalog()["diagrams"]
    }


def compact_payload(kind, canonical):
    payload = deepcopy(canonical)
    if kind == "state-machine":
        payload.update(states=[{"id": "i", "type": "initial"}, {"id": "f", "type": "final"}], transitions=[{"id": "go", "source": "i", "target": "f"}])
        payload.pop("focus", None)
    elif kind == "swimlane":
        payload.update(lanes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], steps=[{"id": "s", "label": "Start", "type": "terminal", "lane": "a"}], flows=[])
        payload.pop("focus_lane", None); payload.pop("focus_path", None)
    elif kind == "tree":
        payload.update(nodes=[{"id": "root", "label": "Root"}], relations=[]); payload.pop("focus_root", None)
    elif kind == "layer-stack":
        payload.update(layers=[{"id": f"l{i}", "label": f"L{i}", "responsibility": "work"} for i in range(3)], flows=[])
    elif kind == "timeline":
        payload.update(events=[{"id": f"e{i}", "date": f"2026-08-0{i + 1}", "label": f"E{i}"} for i in range(3)]); payload.pop("focus", None)
    elif kind == "quadrant":
        payload["items"] = [{"id": f"p{i}", "label": f"P{i}", "x": 0.2 + (i % 2) * 0.6, "y": 0.2 + (i // 2) * 0.6} for i in range(4)]
    elif kind == "venn":
        payload.update(sets=[{"id": "a", "label": "A", "exclusive": ["a"]}, {"id": "b", "label": "B", "exclusive": ["b"]}], intersections=[{"id": "ab", "sets": ["a", "b"], "items": ["shared"]}], focus=[])
    elif kind == "pyramid":
        payload.update(levels=[{"id": f"l{i}", "label": f"L{i}"} for i in range(3)]); payload.pop("focus", None)
    elif kind == "org-chart":
        payload.update(units=[{"id": "root", "label": "Root"}, {"id": "a", "label": "A", "parent": "root"}, {"id": "b", "label": "B", "parent": "root"}]); payload.pop("focus", None)
    elif kind == "loop-flywheel":
        payload.update(stages=[{"id": f"s{i}", "label": f"S{i}"} for i in range(3)]); payload.pop("focus", None); payload.pop("hub", None)
    elif kind == "scatter":
        payload.update(points=[{"id": f"p{i}", "label": f"P{i}", "x": i, "y": i * 2} for i in range(3)]); payload.pop("focus", None)
    elif kind == "gantt":
        payload.update(periods=["P1", "P2", "P3"], tasks=[{"id": f"t{i}", "label": f"T{i}", "start": i, "span": 1} for i in range(3)], milestones=[]); payload.pop("focus", None)
    elif kind == "heatmap":
        payload.update(
            columns=["C1", "C2", "C3"],
            rows=[{"id": f"r{i}", "label": f"R{i}", "values": [i, i + 1, i + 2]} for i in range(3)],
        ); payload.pop("focus", None)
    elif kind == "bar-chart":
        payload.update(categories=["A"], series=[{"id": "s", "label": "S", "values": [1]}]); payload.pop("focus_series", None)
    elif kind == "line-chart":
        payload.update(categories=["A", "B"], series=[{"id": "s", "label": "S", "values": [1, 2]}]); payload.pop("focus_series", None)
    elif kind == "donut-chart":
        payload.update(segments=[{"id": "a", "label": "A", "value": 1}, {"id": "b", "label": "B", "value": 1}]); payload.pop("focus_segment", None)
    elif kind == "candlestick":
        payload["periods"] = [{"id": "d", "date": "2026-08-01", "open": 2, "high": 3, "low": 1, "close": 2.5}]
    elif kind == "waterfall":
        payload.update(start=10, contributions=[{"id": "a", "label": "A", "value": 2}], end=12)
    elif kind == "sequence":
        payload.update(
            participants=[{"id": "a", "label": "A", "kind": "actor"}, {"id": "b", "label": "B", "kind": "system"}],
            messages=[{"id": "m", "source": "a", "target": "b", "label": "Call", "kind": "sync"}],
        ); payload.pop("focus_participant", None)
    elif kind == "uml-class":
        payload.update(types=[{"id": "a", "kind": "class", "name": "A"}], relationships=[])
        payload.pop("focus", None)
    elif kind == "er-diagram":
        payload.update(
            entities=[
                {"id": "a", "name": "A", "fields": [{"id": "id", "name": "id", "type": "uuid", "primary_key": True}]},
                {"id": "b", "name": "B", "fields": [{"id": "id", "name": "id", "type": "uuid", "primary_key": True}]},
            ],
            relationships=[{"id": "r", "source": "a", "target": "b", "label": "owns", "source_cardinality": "one", "target_cardinality": "many"}],
        ); payload.pop("focus_entity", None)
    return payload


def dense_payload(kind, canonical):
    payload = deepcopy(canonical)
    if kind == "state-machine":
        states = [{"id": "i", "type": "initial"}, {"id": "hub", "type": "state", "label": "Hub"}]
        states += [{"id": name, "type": "state", "label": name.upper()} for name in ("a", "b", "c", "d", "e", "g")]
        states += [{"id": "z", "type": "final"}]
        transitions = [{"id": "i-h", "source": "i", "target": "hub"}]
        transitions += [{"id": f"h-{name}", "source": "hub", "target": name} for name in "abc"]
        transitions += [{"id": f"{name}-d", "source": name, "target": "d"} for name in ("a", "b", "c")]
        transitions += [
            {"id": "d-e", "source": "d", "target": "e"},
            {"id": "e-g", "source": "e", "target": "g"},
            {"id": "g-z", "source": "g", "target": "z"},
        ]
        payload.update(states=states, transitions=transitions); payload.pop("focus", None)
    elif kind == "swimlane":
        lanes = [{"id": f"l{i}", "label": f"Lane {i}"} for i in range(5)]
        lane_order = (0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 0, 0)
        steps = [{"id": f"s{i}", "label": f"Step {i}", "type": "action", "lane": f"l{lane_order[i]}"} for i in range(12)]
        flows = [{"id": f"f{i}", "source": f"s{i}", "target": f"s{i + 1}", "channel": "request"} for i in range(11)]
        payload.update(lanes=lanes, steps=steps, flows=flows); payload.pop("focus_lane", None); payload.pop("focus_path", None)
    elif kind == "tree":
        nodes = [{"id": "root", "label": "Root"}]
        nodes += [{"id": f"a{i}", "label": f"A{i}"} for i in range(5)]
        nodes += [{"id": f"b{i}", "label": f"B{i}"} for i in range(5)]
        nodes += [{"id": f"c{i}", "label": f"C{i}"} for i in range(4)]
        relations = [{"id": f"r-a{i}", "parent": "root", "child": f"a{i}"} for i in range(5)]
        relations += [{"id": f"a-b{i}", "parent": f"a{i}", "child": f"b{i}"} for i in range(5)]
        relations += [{"id": f"b-c{i}", "parent": f"b{i}", "child": f"c{i}"} for i in range(4)]
        payload.update(nodes=nodes, relations=relations); payload.pop("focus_root", None)
    elif kind == "layer-stack":
        layers = [{"id": f"l{i}", "label": f"Layer {i}", "responsibility": f"Responsibility {i}"} for i in range(7)]
        payload.update(layers=layers, flows=[{"id": f"f{i}", "source": f"l{i}", "target": f"l{i + 1}", "channel": "request"} for i in range(6)])
    elif kind == "timeline":
        payload.update(scale="ordinal", events=[{"id": f"e{i}", "date": str(date(2026, 8, 1) + timedelta(days=i)), "label": f"E{i}"} for i in range(10)]); payload.pop("focus", None)
    elif kind == "quadrant":
        payload["items"] = [{"id": f"p{i}", "label": f"P{i}", "x": 0.12 + (i % 4) * 0.24, "y": 0.16 + (i // 4) * 0.32} for i in range(12)]
    elif kind == "venn":
        payload.update(
            sets=[{"id": item, "label": item.upper(), "exclusive": [f"{item}1", f"{item}2", f"{item}3"]} for item in "abc"],
            intersections=[
                {"id": "ab", "sets": ["a", "b"], "items": ["ab1", "ab2"]},
                {"id": "ac", "sets": ["a", "c"], "items": ["ac1"]},
                {"id": "bc", "sets": ["b", "c"], "items": ["bc1"]},
                {"id": "abc", "sets": ["a", "b", "c"], "items": ["all"]},
            ], focus=[],
        )
    elif kind == "pyramid":
        payload.update(levels=[{"id": f"l{i}", "label": f"Level {i}", "detail": f"Detail line {i}"} for i in range(6)]); payload.pop("focus", None)
    elif kind == "org-chart":
        units = [{"id": "root", "label": "Root", "role": "director"}]
        units += [{"id": f"m{i}", "label": f"Manager {i}", "role": "lead", "parent": "root"} for i in range(3)]
        units += [{"id": f"ic{i}", "label": f"IC {i}", "role": "ic", "parent": f"m{i % 3}"} for i in range(6)]
        payload.update(units=units); payload.pop("focus", None)
    elif kind == "loop-flywheel":
        payload.update(hub="Hub", stages=[{"id": f"s{i}", "label": f"Stage {i}", "detail": f"Detail {i}"} for i in range(6)]); payload.pop("focus", None)
    elif kind == "scatter":
        payload.update(points=[{"id": f"p{i}", "label": f"Point {i}", "x": i * 3, "y": (i % 5) * 7 + 4} for i in range(14)]); payload.pop("focus", None)
    elif kind == "gantt":
        payload.update(
            periods=[f"W{i}" for i in range(12)],
            tasks=[{"id": f"t{i}", "label": f"Task {i}", "start": i, "span": 2, "track": f"tr{i}"} for i in range(10)],
            milestones=[{"id": "m1", "label": "Mid", "at": 6}],
        ); payload.pop("focus", None)
    elif kind == "heatmap":
        payload.update(
            columns=[f"W{i}" for i in range(12)],
            rows=[
                {"id": f"r{i}", "label": f"Row {i}", "values": [(i * 7 + j * 3) % 40 for j in range(12)]}
                for i in range(10)
            ],
        ); payload.pop("focus", None)
    elif kind in {"bar-chart", "line-chart"}:
        count = 8 if kind == "bar-chart" else 12
        payload.update(categories=[f"C{i}" for i in range(count)], series=[{"id": f"s{j}", "label": f"S{j}", "values": [i * (j + 1) - 3 for i in range(count)]} for j in range(3)])
        payload.pop("focus_series", None)
    elif kind == "donut-chart":
        payload.update(segments=[{"id": f"s{i}", "label": f"S{i}", "value": i + 1} for i in range(6)]); payload.pop("focus_segment", None)
    elif kind == "candlestick":
        payload["periods"] = [{"id": f"d{i}", "date": str(date(2026, 1, 1) + timedelta(days=i)), "open": 100 + i, "high": 104 + i, "low": 98 + i, "close": 102 + i} for i in range(30)]
    elif kind == "waterfall":
        values = [4, -2, 5, -1, 3, 2, -4, 6]
        payload.update(start=20, contributions=[{"id": f"c{i}", "label": f"C{i}", "value": value} for i, value in enumerate(values)], end=20 + sum(values))
    elif kind == "sequence":
        participants = [{"id": f"p{i}", "label": f"P{i}", "kind": "system"} for i in range(6)]
        messages = [{"id": f"m{i}", "source": f"p{i % 6}", "target": f"p{(i + 1) % 6}", "label": f"M{i}", "kind": "sync"} for i in range(12)]
        payload.update(participants=participants, messages=messages); payload.pop("focus_participant", None)
    elif kind == "uml-class":
        types = [{"id": f"t{i}", "kind": "class", "name": f"Type{i}", "attributes": ["id: uuid"], "methods": ["run(): void"]} for i in range(8)]
        relationships = [{"id": f"r{i}", "source": f"t{i}", "target": f"t{i + 1}", "kind": "association"} for i in range(7)]
        payload.update(types=types, relationships=relationships); payload.pop("focus", None)
    elif kind == "er-diagram":
        entities = [{"id": f"e{i}", "name": f"Entity{i}", "fields": [{"id": "id", "name": "id", "type": "uuid", "primary_key": True}, {"id": "name", "name": "name", "type": "text"}]} for i in range(8)]
        relationships = [{"id": f"r{i}", "source": f"e{i}", "target": f"e{i + 1}", "label": "R", "source_cardinality": "one", "target_cardinality": "many"} for i in range(7)]
        payload.update(entities=entities, relationships=relationships); payload.pop("focus_entity", None)
    return payload


def overflow_payload(kind, canonical):
    payload = dense_payload(kind, canonical)
    if kind == "state-machine": payload["states"].insert(-1, {"id": "extra", "type": "state", "label": "Extra"})
    elif kind == "swimlane": payload["lanes"].append({"id": "extra", "label": "Extra"})
    elif kind == "tree": payload["nodes"].append({"id": "extra", "label": "Extra"})
    elif kind == "layer-stack": payload["layers"].append({"id": "extra", "label": "Extra", "responsibility": "Extra"})
    elif kind == "timeline": payload["events"].append({"id": "extra", "date": "2026-09-01", "label": "Extra"})
    elif kind == "quadrant": payload["items"].append({"id": "extra", "label": "Extra", "x": 0.5, "y": 0.5})
    elif kind == "venn": payload["sets"].append({"id": "d", "label": "D", "exclusive": []})
    elif kind == "pyramid": payload["levels"].append({"id": "extra", "label": "Extra"})
    elif kind == "org-chart": payload["units"] += [{"id": f"x{i}", "label": f"X{i}", "parent": f"ic{i}"} for i in range(6)] + [{"id": "y", "label": "Y", "parent": "x0"}]
    elif kind == "loop-flywheel": payload["stages"].append({"id": "extra", "label": "Extra"})
    elif kind == "scatter": payload["points"].append({"id": "extra", "label": "Extra", "x": 1, "y": 1})
    elif kind == "gantt": payload["tasks"].append({"id": "extra", "label": "Extra", "start": 0, "span": 1})
    elif kind == "heatmap": payload["rows"].append({"id": "extra", "label": "Extra", "values": [1] * len(payload["columns"])})
    elif kind in {"bar-chart", "line-chart"}: payload["categories"].append("Extra"); [item["values"].append(1) for item in payload["series"]]
    elif kind == "donut-chart": payload["segments"].append({"id": "extra", "label": "Extra", "value": 1})
    elif kind == "candlestick": payload["periods"].append({"id": "extra", "date": "2026-12-31", "open": 1, "high": 2, "low": 0, "close": 1})
    elif kind == "waterfall": payload["contributions"].append({"id": "extra", "label": "Extra", "value": 1}); payload["end"] += 1
    elif kind == "sequence": payload["participants"].append({"id": "extra", "label": "Extra", "kind": "system"})
    elif kind == "uml-class": payload["types"].append({"id": "extra", "kind": "class", "name": "Extra"})
    elif kind == "er-diagram": payload["entities"].append({"id": "extra", "name": "Extra", "fields": [{"id": "id", "name": "id", "type": "uuid", "primary_key": True}]})
    return payload


def localized_payload(canonical, mixed=False):
    payload = deepcopy(canonical)
    payload["title"] = "中文 API 图表" if mixed else "中文图表"
    payload["language"] = "zh-CN"
    for key in ("states", "lanes", "steps", "nodes", "layers", "events", "items", "sets", "series", "segments", "contributions", "participants", "messages", "relationships", "levels", "units", "stages", "points", "tasks", "rows"):
        for index, item in enumerate(payload.get(key, [])):
            if "label" in item:
                item["label"] = f"节点 {index} API" if mixed else f"节点{index}"
            if "responsibility" in item:
                item["responsibility"] = "处理 API 请求" if mixed else "处理请求"
    for index, item in enumerate(payload.get("types", [])):
        item["name"] = f"类型 {index} API" if mixed else f"类型{index}"
    for index, item in enumerate(payload.get("entities", [])):
        item["name"] = f"实体 {index} API" if mixed else f"实体{index}"
        for field_index, field in enumerate(item.get("fields", [])):
            field["name"] = f"字段{field_index}"
    if isinstance(payload.get("axes"), dict):
        for axis in payload["axes"].values():
            axis.update(label="能力", low="低", high="高")
    return payload


class DrawingDslV3Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = catalog_payloads()

    def test_registry_and_catalog_cover_all_declared_types(self):
        self.assertEqual(ALL_KINDS, set(DEFAULT_COMPILER_REGISTRY.kinds))
        self.assertEqual(ALL_KINDS, set(self.payloads))

    def test_canonical_compact_dense_cjk_and_mixed_fixtures_compile(self):
        for kind in sorted(NEW_KINDS):
            for fixture_class, payload in (
                ("canonical", self.payloads[kind]),
                ("compact", compact_payload(kind, self.payloads[kind])),
                ("dense", dense_payload(kind, self.payloads[kind])),
                ("cjk", localized_payload(self.payloads[kind])),
                ("mixed", localized_payload(self.payloads[kind], mixed=True)),
            ):
                with self.subTest(kind=kind, fixture=fixture_class):
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                    self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                    self.assertEqual(len(result.scene.reading_order), len(set(result.scene.reading_order)))
                    self.assertIn('data-folio-id="drawing-description"', render_svg(result.scene))

    def test_overflow_and_invalid_contracts_fail_closed(self):
        for kind in sorted(NEW_KINDS):
            overflow = overflow_payload(kind, self.payloads[kind])
            invalid = deepcopy(self.payloads[kind])
            invalid["unexpected"] = True
            for fixture_class, payload in (("overflow", overflow), ("invalid", invalid)):
                with self.subTest(kind=kind, fixture=fixture_class), self.assertRaises(DrawingCompilationError):
                    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

    def test_compilation_and_scale_snapshots_are_deterministic(self):
        for kind, payload in self.payloads.items():
            with self.subTest(kind=kind):
                left = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                right = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertEqual(left.metadata.input_sha256, right.metadata.input_sha256)
                self.assertEqual(left.plan.to_dict(), right.plan.to_dict())
                self.assertEqual(render_svg(left.scene), render_svg(right.scene))

    def test_explicit_cjk_structural_fixtures_compile(self):
        for name in ("state-machine-cjk.json", "swimlane-cjk.json"):
            payload = json.loads((ROOT / "references" / "fixtures" / "v3" / name).read_text(encoding="utf-8"))
            result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
            self.assertEqual("zh-CN", result.scene.language)

    def test_data_numerical_edge_cases(self):
        cases = []
        bar = deepcopy(self.payloads["bar-chart"]); bar["series"][0]["values"] = [0, -2, 3, -4, 5]; cases.append(bar)
        line = deepcopy(self.payloads["line-chart"]); line["series"][0]["values"][2] = None; line["missing_policy"] = "gap"; cases.append(line)
        donut = deepcopy(self.payloads["donut-chart"]); donut.update(percent_total=True, tolerance=0.1); [item.update(value=value) for item, value in zip(donut["segments"], (25.0, 25.0, 25.0, 25.0))]; cases.append(donut)
        candle = deepcopy(self.payloads["candlestick"]); candle["periods"][0].update(open=1e9, high=1.1e9, low=0.9e9, close=1.05e9); cases.append(candle)
        waterfall = deepcopy(self.payloads["waterfall"]); waterfall.update(start=0.1, contributions=[{"id": "a", "label": "A", "value": 0.2}], end=0.3, tolerance=1e-9); cases.append(waterfall)
        for payload in cases:
            with self.subTest(kind=payload["kind"]):
                DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

        invalid = []
        bar = deepcopy(self.payloads["bar-chart"]); bar["series"][0]["values"][0] = math.nan; invalid.append(bar)
        line = deepcopy(self.payloads["line-chart"]); line["series"][0]["values"][0] = None; line["missing_policy"] = "error"; invalid.append(line)
        donut = deepcopy(self.payloads["donut-chart"]); donut["segments"][0]["value"] = 0; invalid.append(donut)
        candle = deepcopy(self.payloads["candlestick"]); candle["periods"][0]["low"] = candle["periods"][0]["high"] + 1; invalid.append(candle)
        waterfall = deepcopy(self.payloads["waterfall"]); waterfall["end"] += 1; invalid.append(waterfall)
        for payload in invalid:
            with self.subTest(kind=payload["kind"]), self.assertRaises(DrawingCompilationError):
                DEFAULT_COMPILER_REGISTRY.compile_payload(payload)

    def test_data_order_and_temporal_spacing_are_semantic(self):
        bar = compact_payload("bar-chart", self.payloads["bar-chart"])
        bar.update(categories=["A", "B", "C"], series=[{"id": "s", "label": "S", "values": [1, 3, 2]}], order=["C", "A", "B"])
        first = DEFAULT_COMPILER_REGISTRY.compile_payload(bar)
        reordered = deepcopy(bar); reordered["order"] = ["A", "B", "C"]
        second = DEFAULT_COMPILER_REGISTRY.compile_payload(reordered)
        self.assertEqual(("C", "A", "B"), first.plan.categories)
        self.assertEqual({item["id"] for item in first.semantic.marks}, {item["id"] for item in second.semantic.marks})

        line = compact_payload("line-chart", self.payloads["line-chart"])
        line.update(categories=["2026-01-01", "2026-01-02", "2026-01-11"], series=[{"id": "s", "label": "S", "values": [1, 2, 3]}], x_scale="time")
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(line)
        points = list(result.layout.x_positions)
        self.assertLess(points[1] - points[0], points[2] - points[1])

        candle = compact_payload("candlestick", self.payloads["candlestick"])
        candle["periods"] = [
            {"id": "a", "date": "2026-01-01", "open": 1, "high": 3, "low": 0, "close": 2},
            {"id": "b", "date": "2026-01-02", "open": 2, "high": 4, "low": 1, "close": 3},
            {"id": "c", "date": "2026-01-11", "open": 3, "high": 5, "low": 2, "close": 4},
        ]
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(candle)
        xs = [result.layout.marks[f"candle:{item}"]["x"] for item in "abc"]
        self.assertLess(xs[1] - xs[0], xs[2] - xs[1])

    def test_published_v3_schema_matches_runtime_kinds(self):
        schema = json.loads((ROOT / "references" / "schemas" / "drawing-payload-v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(len(NEW_KINDS), len(schema["oneOf"]))
        schema_kinds = {schema["$defs"][name]["properties"]["kind"]["const"] for name in NEW_KINDS}
        self.assertEqual(NEW_KINDS, schema_kinds)
        self.assertTrue(all(schema["$defs"][name]["additionalProperties"] is False for name in NEW_KINDS))

    def test_tree_siblings_share_one_bus(self):
        payload = self.payloads["tree"]
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
        self.assertEqual((), result.scene.edges)
        self.assertEqual(len(payload["relations"]), result.metrics.edges)
        links = {
            item.id[len("link:"):]: item.points
            for item in result.scene.primitives
            if isinstance(item, ScenePolyline) and item.id.startswith("link:")
        }
        self.assertEqual({item["child"] for item in payload["relations"]}, set(links))
        boxes = {node.id: node.box for node in result.scene.nodes}
        groups = {}
        for relation in payload["relations"]:
            groups.setdefault(relation["parent"], []).append(relation["child"])
        for parent, children in groups.items():
            with self.subTest(parent=parent):
                trunks = {links[child][0] for child in children}
                self.assertEqual(1, len(trunks))
                trunk_x, trunk_y = trunks.pop()
                parent_box = boxes[parent]
                self.assertEqual(parent_box.x + parent_box.w // 2, trunk_x)
                self.assertEqual(parent_box.y + parent_box.h, trunk_y)
                bus_levels = {
                    links[child][1][1] if len(links[child]) >= 3 else links[child][0][1]
                    for child in children
                }
                self.assertEqual(1, len(bus_levels))
                bus_y = bus_levels.pop()
                self.assertGreaterEqual(bus_y, trunk_y)
                for child in children:
                    points = links[child]
                    self.assertGreaterEqual(len(points), 2)
                    drop_x, drop_y = points[-1]
                    child_box = boxes[child]
                    self.assertEqual(child_box.y, drop_y)
                    self.assertLessEqual(child_box.x, drop_x)
                    self.assertLessEqual(drop_x, child_box.x + child_box.w)
                    self.assertLessEqual(bus_y, drop_y)

    def test_all_types_three_profiles_three_formats_matrix(self):
        artifact_count = 0
        with TemporaryDirectory() as temp:
            output = Path(temp)
            for kind, payload in self.payloads.items():
                for profile in ("artifact", "embed", "page-preview"):
                    with self.subTest(kind=kind, profile=profile):
                        result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile)
                        stem = f"{kind}-{profile}"
                        svg_path, png_path, pdf_path = (output / f"{stem}.{suffix}" for suffix in ("svg", "png", "pdf"))
                        svg_path.write_text(render_svg(result.scene, profile), encoding="utf-8")
                        export_png(svg_path, png_path, profile=profile, title=result.plan.title, language=result.plan.language)
                        export_pdf(svg_path, pdf_path, result.plan.title, result.plan.language, profile)
                        artifact_count += 3
                        self.assertGreater(svg_path.stat().st_size, 100)
                        with Image.open(png_path) as image:
                            self.assertEqual((1241, 1754) if profile == "page-preview" else 1920, image.size if profile == "page-preview" else image.width)
                        reader = PdfReader(str(pdf_path))
                        self.assertEqual(1, len(reader.pages))
                        page = reader.pages[0]
                        if profile == "page-preview":
                            self.assertAlmostEqual(595.28, float(page.mediabox.width), delta=1)
                            self.assertAlmostEqual(841.89, float(page.mediabox.height), delta=1)
            self.assertEqual(len(self.payloads) * 3 * 3, artifact_count)

    def test_indistinguishable_parallel_edges_fail_closed(self):
        cases = (
            ("architecture", "edges", "DG042", {"label": "distinct"}),
            ("flowchart", "edges", "FC019", {"label": "distinct"}),
            ("layer-stack", "flows", "LS009", {"label": "distinct"}),
            ("state-machine", "transitions", "SM023", {"event": "distinct"}),
            ("swimlane", "flows", "SW020", {"label": "distinct"}),
        )
        for kind, collection, code, distinct in cases:
            duplicated = deepcopy(self.payloads[kind])
            clone = deepcopy(duplicated[collection][0])
            if "id" in clone:
                clone["id"] = f"{clone['id']}-dupe"
            duplicated[collection].append(clone)
            with self.subTest(kind=kind, edges="indistinguishable"):
                with self.assertRaises(DrawingCompilationError) as caught:
                    DEFAULT_COMPILER_REGISTRY.compile_payload(duplicated)
                self.assertIn(code, {item.code for item in caught.exception.diagnostics})
            distinguished = deepcopy(duplicated)
            distinguished[collection][-1].update(distinct)
            with self.subTest(kind=kind, edges="distinguished"):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(distinguished)
                self.assertFalse([item for item in result.diagnostics if item.level == "ERROR"])
                self.assertEqual(len(distinguished[collection]), result.metrics.edges)

    def test_self_edges_fail_closed(self):
        cases = (
            ("architecture", "edges", "DG043", {"source": "gateway", "target": "gateway", "kind": "primary"}),
            ("flowchart", "edges", "FC020", {"source": "publish", "target": "publish", "kind": "sequence-flow"}),
            ("layer-stack", "flows", "LS010", {"id": "self", "source": "render", "target": "render", "channel": "request"}),
            ("state-machine", "transitions", "SM024", {"id": "self", "source": "rendering", "target": "rendering"}),
            ("swimlane", "flows", "SW021", {"id": "self", "source": "reconcile", "target": "reconcile", "channel": "request"}),
        )
        for kind, collection, code, self_edge in cases:
            payload = deepcopy(self.payloads[kind])
            payload[collection].append(self_edge)
            with self.subTest(kind=kind):
                with self.assertRaises(DrawingCompilationError) as caught:
                    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
                self.assertIn(code, {item.code for item in caught.exception.diagnostics})
