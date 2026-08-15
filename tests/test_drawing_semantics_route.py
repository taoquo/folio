import importlib.util
import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.semantics import (
    AUDIENCES,
    GOALS,
    PATTERN_KEYWORDS,
    PATTERN_KINDS,
    SEMANTIC_PATTERNS,
    DataShape,
    RouteRequest,
    normalize_pattern,
    pattern_of_kind,
    route_from_dict,
    route_semantic_pattern,
)

SPEC = importlib.util.spec_from_file_location("folio_cli_route", SCRIPTS_DIR / "folio.py")
folio = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = folio
SPEC.loader.exec_module(folio)


def _codes(decision) -> list[str]:
    return [item.code for item in decision.diagnostics]


class SemanticPatternVocabularyTests(TestCase):
    def test_v5_pattern_tables_are_complete_sorted_and_registry_backed(self) -> None:
        self.assertEqual(sorted(SEMANTIC_PATTERNS), list(SEMANTIC_PATTERNS))
        self.assertEqual(set(SEMANTIC_PATTERNS), set(PATTERN_KINDS))
        self.assertEqual(set(SEMANTIC_PATTERNS), set(PATTERN_KEYWORDS))

        registered = set(DEFAULT_COMPILER_REGISTRY.kinds)
        for pattern, kinds in PATTERN_KINDS.items():
            with self.subTest(pattern=pattern):
                self.assertTrue(kinds)
                self.assertEqual(len(set(kinds)), len(kinds))
                self.assertTrue(set(kinds) <= registered)

    def test_v5_every_pattern_carries_english_and_chinese_cues(self) -> None:
        for pattern, words in PATTERN_KEYWORDS.items():
            with self.subTest(pattern=pattern):
                ascii_cues = [word for word in words if word.strip().isascii()]
                cjk_cues = [word for word in words if any("\u4e00" <= ch <= "\u9fff" for ch in word)]
                self.assertTrue(ascii_cues)
                self.assertTrue(cjk_cues)

    def test_v5_pattern_helpers_normalize_and_reverse_lookup(self) -> None:
        self.assertEqual("flow", normalize_pattern("  FLOW "))
        self.assertIsNone(normalize_pattern("mind-map"))
        self.assertIsNone(normalize_pattern(None))
        self.assertEqual("state", pattern_of_kind("state-machine"))
        self.assertIsNone(pattern_of_kind("mind-map"))


class SemanticRoutingTests(TestCase):
    def test_v5_each_pattern_routes_from_an_english_brief(self) -> None:
        cases = {
            "architecture": RouteRequest(
                content="system architecture with gateway service and worker components",
                shape=DataShape(node_count=6, edge_count=6),
            ),
            "comparison": RouteRequest(
                content="compare the tradeoff between two vendor options",
                goal="compare",
            ),
            "data": RouteRequest(
                content="quarterly revenue growth metrics by region",
                shape=DataShape(series_count=2, category_count=4, numeric=True),
            ),
            "flow": RouteRequest(content="the review process runs step by step through a pipeline"),
            "hierarchy": RouteRequest(
                content="team reporting hierarchy breakdown",
                shape=DataShape(depth=3),
            ),
            "relationship": RouteRequest(
                content="entity schema relationship between orders and customers",
                shape=DataShape(node_count=4, edge_count=4),
            ),
            "state": RouteRequest(
                content="order lifecycle state transition with retry",
                shape=DataShape(node_count=4, has_cycle=True),
            ),
            "time": RouteRequest(content="release roadmap milestone schedule"),
        }
        for pattern, request in cases.items():
            with self.subTest(pattern=pattern):
                decision = route_semantic_pattern(request)
                self.assertEqual(pattern, decision.pattern)
                self.assertIn(decision.kind, PATTERN_KINDS[pattern])
                self.assertNotIn("RT001", _codes(decision))

    def test_v5_chinese_briefs_route_to_the_same_patterns_as_english(self) -> None:
        pairs = [
            ("the deployment architecture of the platform", "平台的部署架构"),
            ("the approval process flow", "审批流程"),
            ("release milestone roadmap", "发布里程碑路线图"),
            ("order lifecycle state machine", "订单生命周期状态机"),
        ]
        for english, chinese in pairs:
            with self.subTest(brief=chinese):
                self.assertEqual(
                    route_semantic_pattern(RouteRequest(content=english)).pattern,
                    route_semantic_pattern(RouteRequest(content=chinese)).pattern,
                )

    def test_v5_shape_signals_pick_the_kind_inside_one_pattern(self) -> None:
        timeline = route_semantic_pattern(RouteRequest(content="release milestone roadmap"))
        self.assertEqual("timeline", timeline.kind)

        trended = route_semantic_pattern(RouteRequest(
            content="release milestone roadmap",
            shape=DataShape(series_count=2, numeric=True),
        ))
        self.assertEqual("line-chart", trended.kind)

        lanes = route_semantic_pattern(RouteRequest(
            content="the handoff process between teams",
            shape=DataShape(has_actors=True),
        ))
        self.assertEqual("swimlane", lanes.kind)

        messages = route_semantic_pattern(RouteRequest(
            content="the handoff process between teams",
            audience="practitioner",
            shape=DataShape(has_actors=True),
        ))
        self.assertEqual("sequence", messages.kind)

    def test_v5_hints_override_weak_keyword_evidence(self) -> None:
        decision = route_semantic_pattern(RouteRequest(
            content="quarterly revenue growth metrics",
            pattern_hint="hierarchy",
            shape=DataShape(depth=3),
        ))
        self.assertEqual("hierarchy", decision.pattern)
        self.assertTrue(any(step.stage == "hint" for step in decision.trace))

        by_kind = route_semantic_pattern(RouteRequest(
            content="quarterly revenue growth metrics",
            kind_hint="tree",
            shape=DataShape(depth=3),
        ))
        self.assertEqual("hierarchy", by_kind.pattern)
        self.assertEqual("tree", by_kind.kind)

    def test_v5_undrawable_brief_is_rejected_with_rt001(self) -> None:
        decision = route_semantic_pattern(RouteRequest(content="please write me a poem about rain"))

        self.assertFalse(decision.routable)
        self.assertIsNone(decision.kind)
        self.assertEqual("none", decision.confidence)
        self.assertIn("RT001", _codes(decision))
        self.assertEqual("ERROR", decision.diagnostics[0].level)

    def test_v5_ambiguous_brief_warns_with_rt002_and_low_confidence(self) -> None:
        decision = route_semantic_pattern(RouteRequest(content="architecture process"))

        self.assertTrue(decision.routable)
        self.assertIn("RT002", _codes(decision))
        self.assertEqual("low", decision.confidence)

    def test_v5_unknown_hints_and_enums_report_their_own_codes(self) -> None:
        bad_pattern = route_semantic_pattern(RouteRequest(content="a process flow", pattern_hint="mind-map"))
        self.assertIn("RT003", _codes(bad_pattern))
        self.assertFalse(bad_pattern.routable)

        bad_kind = route_semantic_pattern(RouteRequest(content="a process flow", kind_hint="mind-map"))
        self.assertIn("RT004", _codes(bad_kind))
        self.assertFalse(bad_kind.routable)

        bad_audience = route_semantic_pattern(RouteRequest(content="a process flow", audience="robots"))
        self.assertIn("RT010", _codes(bad_audience))
        self.assertTrue(bad_audience.routable)

        bad_goal = route_semantic_pattern(RouteRequest(content="a process flow", goal="delight"))
        self.assertIn("RT011", _codes(bad_goal))
        self.assertTrue(bad_goal.routable)

    def test_v5_routing_is_deterministic_and_fully_traced(self) -> None:
        request = RouteRequest(
            content="quarterly revenue growth by region",
            audience="executive",
            goal="compare",
            shape=DataShape(series_count=1, category_count=4, numeric=True),
        )
        first = route_semantic_pattern(request)
        second = route_semantic_pattern(request)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(SEMANTIC_PATTERNS), len(first.scores))
        self.assertEqual(
            sorted(SEMANTIC_PATTERNS), sorted(name for name, _score in first.scores)
        )
        stages = {step.stage for step in first.trace}
        self.assertIn("pattern", stages)
        self.assertIn("kind", stages)
        self.assertNotIn(first.kind, first.alternatives)

    def test_v5_route_from_dict_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValueError):
            route_from_dict({"content": "a process flow", "style": "dark"})
        with self.assertRaises(ValueError):
            route_from_dict({"content": "a process flow", "shape": {"pixels": 10}})
        with self.assertRaises(ValueError):
            route_from_dict({"content": "a process flow", "shape": "wide"})

        decision = route_from_dict({"content": "a process flow", "audience": "practitioner"})
        self.assertEqual("flow", decision.pattern)

    def test_v5_route_request_schema_matches_the_router_contract(self) -> None:
        schema = json.loads((ROOT / "references/schemas/route-request.schema.json").read_text(encoding="utf-8"))

        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(list(AUDIENCES), schema["properties"]["audience"]["enum"])
        self.assertEqual(list(GOALS), schema["properties"]["goal"]["enum"])
        self.assertEqual(
            list(SEMANTIC_PATTERNS),
            schema["properties"]["pattern_hint"]["oneOf"][1]["enum"],
        )
        self.assertEqual(
            sorted(DataShape().to_dict()),
            sorted(schema["properties"]["shape"]["properties"]),
        )


class RouteDiagramCliTests(TestCase):
    def test_v5_cli_text_output_explains_the_decision(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            code = folio.main(["folio.py", "route-diagram", "--content", "the approval process flow"])

        self.assertEqual(0, code)
        rendered = output.getvalue()
        self.assertIn("OK: flow -> flowchart", rendered)
        self.assertIn("pattern:", rendered)

    def test_v5_cli_json_output_is_machine_readable_and_written_to_disk(self) -> None:
        with TemporaryDirectory() as temp:
            target = Path(temp) / "route.json"
            request = Path(temp) / "request.json"
            request.write_text(
                json.dumps({"content": "quarterly revenue by region", "shape": {"numeric": True, "series_count": 2}}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                code = folio.main([
                    "folio.py", "route-diagram", str(request),
                    "--format", "json", "--output", str(target),
                ])

            self.assertEqual(0, code)
            record = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual("data", record["pattern"])
            self.assertIn(record["kind"], PATTERN_KINDS["data"])
            self.assertEqual(len(SEMANTIC_PATTERNS), len(record["scores"]))
            self.assertTrue(record["trace"])

    def test_v5_cli_reports_unroutable_briefs_with_a_nonzero_code(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            code = folio.main(["folio.py", "route-diagram", "--content", "write me a poem about rain"])

        self.assertNotEqual(0, code)
        self.assertIn("ERROR", output.getvalue())

    def test_v5_cli_rejects_a_missing_request_file(self) -> None:
        errors = io.StringIO()
        with mock.patch("sys.stderr", errors):
            code = folio.main(["folio.py", "route-diagram", "/nonexistent/route-request.json"])

        self.assertNotEqual(0, code)
        self.assertIn("ERROR", errors.getvalue())
