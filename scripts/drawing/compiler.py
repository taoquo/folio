from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from typing import Any, Callable

from diagram_models import ArchitectureDiagramSpec, load_diagram_spec

from .flowchart import compile_flowchart_payload, validate_flowchart
from .dataviz import (
    compile_bar_payload,
    compile_candlestick_payload,
    compile_donut_payload,
    compile_gantt_payload,
    compile_line_payload,
    compile_scatter_payload,
    compile_waterfall_payload,
)
from .models import DrawingPlan
from .migrations import migrate_authoring_payload
from .notation import compile_er_payload, compile_sequence_payload, compile_uml_class_payload
from .pipeline import compile_architecture, compile_drawing_plan
from .output import apply_output_knobs, normalize_output_audience, normalize_output_detail, normalize_output_profile
from .positional import compile_quadrant_payload, compile_timeline_payload, compile_venn_payload
from .theme import DEFAULT_FOLIO_THEME, normalize_theme_profile, resolve_theme, retheme_scene
from .schematic import (
    compile_loop_flywheel_payload,
    compile_org_chart_payload,
    compile_pyramid_payload,
)
from .structural import (
    compile_layer_stack_payload,
    compile_state_machine_payload,
    compile_swimlane_payload,
    compile_tree_payload,
)
from .validation import (
    DrawingCompilationError,
    DrawingDiagnostic,
    DrawingMetrics,
    collect_metrics,
    collect_scene_metrics,
    diagnose_taste,
    validate_canvas,
    validate_drawing_grammar,
    validate_drawing_semantics,
    validate_scene_accessibility,
    validate_scene_geometry,
    validate_scene_primitives,
    validate_scene_quality,
    raise_for_errors,
)


@dataclass(frozen=True)
class CompilationMetadata:
    compiler_contract: str
    input_schema_version: str
    registry_key: str
    input_sha256: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CompilationResult:
    kind: str
    semantic: Any
    plan: Any
    layout: Any
    scene: Any
    diagnostics: tuple[DrawingDiagnostic, ...]
    metrics: DrawingMetrics
    profile: str = "artifact"
    theme: str = "folio"
    detail: str = "full"
    audience: str = "general"
    normalized_input: dict[str, Any] | None = None
    metadata: CompilationMetadata | None = None

    def __iter__(self):
        yield self.semantic
        yield self.plan
        yield self.layout
        yield self.scene


Compiler = Callable[[dict[str, Any]], CompilationResult]


class DiagramCompilerRegistry:
    def __init__(self) -> None:
        self._compilers: dict[str, Compiler] = {}

    def register(self, kind: str, compiler: Compiler) -> None:
        if not kind or kind in self._compilers:
            raise ValueError(f"diagram compiler already registered or invalid: {kind}")
        self._compilers[kind] = compiler

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._compilers))

    def compile_payload(
        self,
        payload: dict[str, Any],
        profile: str = "artifact",
        theme: str = "folio",
        detail: str = "full",
        audience: str = "general",
    ) -> CompilationResult:
        profile = normalize_output_profile(profile)
        theme = normalize_theme_profile(theme)
        detail = normalize_output_detail(detail)
        audience = normalize_output_audience(audience)
        if not isinstance(payload, dict):
            diagnostic = DrawingDiagnostic("ERROR", "CP000", "diagram input must be an object")
            raise DrawingCompilationError("dispatch", (diagnostic,))
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in self._compilers:
            diagnostic = DrawingDiagnostic("ERROR", "CP001", "unknown or missing diagram kind", str(kind))
            raise DrawingCompilationError("dispatch", (diagnostic,))
        if "composition" in payload and "schema_version" not in payload:
            diagnostic = DrawingDiagnostic("ERROR", "CP003", "authored drawing plans require an explicit schema_version", kind)
            raise DrawingCompilationError("schema", (diagnostic,))
        try:
            payload = migrate_authoring_payload(payload)
            result = self._compilers[kind](payload)
            normalized = result.plan.to_dict() if kind == "architecture" and "composition" in payload else deepcopy(payload)
            return self._finalize(result, normalized, profile, theme, detail, audience)
        except DrawingCompilationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            diagnostic = DrawingDiagnostic("ERROR", "CP002", str(exc) or type(exc).__name__)
            raise DrawingCompilationError("input", (diagnostic,)) from exc

    def compile_architecture_spec(
        self,
        spec: ArchitectureDiagramSpec,
        profile: str = "artifact",
        theme: str = "folio",
        detail: str = "full",
        audience: str = "general",
    ) -> CompilationResult:
        profile = normalize_output_profile(profile)
        theme = normalize_theme_profile(theme)
        detail = normalize_output_detail(detail)
        audience = normalize_output_audience(audience)
        semantic, plan, layout, scene = compile_architecture(spec)
        return self._finalize(_architecture_result(semantic, plan, layout, scene), asdict(spec), profile, theme, detail, audience)

    def _finalize(
        self,
        result: CompilationResult,
        normalized_input: dict[str, Any],
        profile: str,
        theme: str = "folio",
        detail: str = "full",
        audience: str = "general",
    ) -> CompilationResult:
        palette = resolve_theme(theme)
        scene = retheme_scene(result.scene, palette, source=DEFAULT_FOLIO_THEME)
        scene = apply_output_knobs(scene, detail=detail, audience=audience)
        result = replace(result, scene=scene)
        diagnostics = _dedupe_diagnostics((*result.diagnostics,
            *validate_canvas(result.scene),
            *validate_scene_primitives(result.scene),
            *validate_scene_accessibility(result.scene),
            *validate_scene_geometry(result.scene),
            *validate_scene_quality(result.scene, palette),
        ))
        raise_for_errors("quality", diagnostics)
        schema_version = str(normalized_input.get("schema_version", getattr(result.plan, "schema_version", "legacy")))
        encoded = json.dumps(normalized_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        metadata = CompilationMetadata(
            compiler_contract="3.0",
            input_schema_version=schema_version,
            registry_key=f"{result.kind}@{schema_version.split('.', 1)[0]}",
            input_sha256=sha256(encoded).hexdigest(),
        )
        return replace(
            result,
            diagnostics=diagnostics,
            metrics=replace(
                result.metrics,
                taste_warnings=sum(
                    item.level in {"WARNING", "TASTE"} for item in diagnostics
                ),
            ),
            profile=profile,
            theme=theme,
            detail=detail,
            audience=audience,
            normalized_input=normalized_input,
            metadata=metadata,
        )


def _dedupe_diagnostics(diagnostics: tuple[DrawingDiagnostic, ...]) -> tuple[DrawingDiagnostic, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[DrawingDiagnostic] = []
    for item in diagnostics:
        key = (item.level, item.code, item.message, item.object_id, item.path, item.hint, item.related_ids)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _architecture(payload: dict[str, Any]) -> CompilationResult:
    if "composition" in payload:
        plan = DrawingPlan.from_dict(payload)
        layout, scene = compile_drawing_plan(plan)
        return _architecture_result(None, plan, layout, scene)
    spec = load_diagram_spec(payload)
    if not isinstance(spec, ArchitectureDiagramSpec):
        raise ValueError("architecture compiler requires an ArchitectureDiagramSpec")
    semantic, plan, layout, scene = compile_architecture(spec)
    return _architecture_result(semantic, plan, layout, scene)


def _architecture_result(semantic: Any, plan: Any, layout: Any, scene: Any) -> CompilationResult:
    diagnostics = tuple([
        *validate_drawing_semantics(plan),
        *validate_drawing_grammar(plan),
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene),
        *diagnose_taste(plan, scene),
    ])
    metrics = collect_metrics(plan, scene, semantic_node_count=len(semantic.nodes) if semantic else len(plan.nodes))
    return CompilationResult("architecture", semantic, plan, layout, scene, diagnostics, metrics)


def _flowchart(payload: dict[str, Any]) -> CompilationResult:
    semantic, plan, layout, scene = compile_flowchart_payload(payload)
    diagnostics = tuple([
        *validate_flowchart(semantic, plan),
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene),
    ])
    taste = sum(item.level in {"WARNING", "TASTE"} for item in diagnostics)
    metrics = collect_metrics(plan, scene, semantic_node_count=len(semantic.nodes), taste_warning_count=taste)
    return CompilationResult("flowchart", semantic, plan, layout, scene, diagnostics, metrics)


def _structural(payload: dict[str, Any], compiler: Callable[[dict[str, Any]], Any]) -> CompilationResult:
    semantic, plan, layout, scene, diagnostics = compiler(payload)
    focus = sum(node.emphasis == "focal" for node in plan.nodes)
    metrics = collect_scene_metrics(
        scene,
        semantic_count=len(semantic.nodes),
        visual_count=len(scene.nodes),
        focus_count=focus,
        taste_warning_count=sum(item.level in {"WARNING", "TASTE"} for item in diagnostics),
    )
    return CompilationResult(plan.kind, semantic, plan, layout, scene, tuple(diagnostics), metrics)


def _positional(payload: dict[str, Any], compiler: Callable[[dict[str, Any]], Any]) -> CompilationResult:
    semantic, plan, layout, scene, diagnostics = compiler(payload)
    focus_value = getattr(plan, "focus", None)
    focus = len(focus_value) if isinstance(focus_value, tuple) else int(bool(focus_value))
    items = getattr(plan, "items", ())
    focus = max(focus, sum(item.get("emphasis") == "focal" for item in items))
    metrics = collect_scene_metrics(
        scene,
        semantic_count=len(semantic.nodes),
        visual_count=len(scene.reading_order),
        focus_count=focus,
        taste_warning_count=sum(item.level in {"WARNING", "TASTE"} for item in diagnostics),
    )
    return CompilationResult(plan.kind, semantic, plan, layout, scene, tuple(diagnostics), metrics)


def _dataviz(payload: dict[str, Any], compiler: Callable[[dict[str, Any]], Any]) -> CompilationResult:
    semantic, plan, layout, scene, diagnostics = compiler(payload)
    focus = int(bool(getattr(plan, "focus_series", None) or getattr(plan, "focus_segment", None)))
    metrics = collect_scene_metrics(
        scene,
        semantic_count=len(semantic.nodes),
        visual_count=len(scene.reading_order),
        focus_count=focus,
        taste_warning_count=sum(item.level in {"WARNING", "TASTE"} for item in diagnostics),
    )
    return CompilationResult(plan.kind, semantic, plan, layout, scene, tuple(diagnostics), metrics)


def _notation(payload: dict[str, Any], compiler: Callable[[dict[str, Any]], Any]) -> CompilationResult:
    semantic, plan, layout, scene, diagnostics = compiler(payload)
    focus = int(bool(payload.get("focus") or payload.get("focus_entity") or payload.get("focus_participant")))
    metrics = collect_scene_metrics(
        scene,
        semantic_count=len(semantic.nodes),
        visual_count=len(scene.reading_order),
        focus_count=focus,
        taste_warning_count=sum(item.level in {"WARNING", "TASTE"} for item in diagnostics),
        edge_count=len(plan.relations),
        edge_label_count=sum(bool(item.get("label")) for item in plan.relations),
        bend_count=sum(max(0, len(points) - 2) for points in layout.relations.values()),
    )
    return CompilationResult(plan.kind, semantic, plan, layout, scene, tuple(diagnostics), metrics)


DEFAULT_COMPILER_REGISTRY = DiagramCompilerRegistry()
DEFAULT_COMPILER_REGISTRY.register("architecture", _architecture)
DEFAULT_COMPILER_REGISTRY.register("flowchart", _flowchart)
DEFAULT_COMPILER_REGISTRY.register("state-machine", lambda payload: _structural(payload, compile_state_machine_payload))
DEFAULT_COMPILER_REGISTRY.register("swimlane", lambda payload: _structural(payload, compile_swimlane_payload))
DEFAULT_COMPILER_REGISTRY.register("tree", lambda payload: _structural(payload, compile_tree_payload))
DEFAULT_COMPILER_REGISTRY.register("layer-stack", lambda payload: _structural(payload, compile_layer_stack_payload))
DEFAULT_COMPILER_REGISTRY.register("timeline", lambda payload: _positional(payload, compile_timeline_payload))
DEFAULT_COMPILER_REGISTRY.register("quadrant", lambda payload: _positional(payload, compile_quadrant_payload))
DEFAULT_COMPILER_REGISTRY.register("venn", lambda payload: _positional(payload, compile_venn_payload))
DEFAULT_COMPILER_REGISTRY.register("pyramid", lambda payload: _positional(payload, compile_pyramid_payload))
DEFAULT_COMPILER_REGISTRY.register("org-chart", lambda payload: _positional(payload, compile_org_chart_payload))
DEFAULT_COMPILER_REGISTRY.register("loop-flywheel", lambda payload: _positional(payload, compile_loop_flywheel_payload))
DEFAULT_COMPILER_REGISTRY.register("bar-chart", lambda payload: _dataviz(payload, compile_bar_payload))
DEFAULT_COMPILER_REGISTRY.register("line-chart", lambda payload: _dataviz(payload, compile_line_payload))
DEFAULT_COMPILER_REGISTRY.register("donut-chart", lambda payload: _dataviz(payload, compile_donut_payload))
DEFAULT_COMPILER_REGISTRY.register("candlestick", lambda payload: _dataviz(payload, compile_candlestick_payload))
DEFAULT_COMPILER_REGISTRY.register("waterfall", lambda payload: _dataviz(payload, compile_waterfall_payload))
DEFAULT_COMPILER_REGISTRY.register("scatter", lambda payload: _dataviz(payload, compile_scatter_payload))
DEFAULT_COMPILER_REGISTRY.register("gantt", lambda payload: _dataviz(payload, compile_gantt_payload))
DEFAULT_COMPILER_REGISTRY.register("sequence", lambda payload: _notation(payload, compile_sequence_payload))
DEFAULT_COMPILER_REGISTRY.register("uml-class", lambda payload: _notation(payload, compile_uml_class_payload))
DEFAULT_COMPILER_REGISTRY.register("er-diagram", lambda payload: _notation(payload, compile_er_payload))
