from __future__ import annotations

from dataclasses import replace

from diagram_models import ArchitectureDiagramSpec

from .adapters import semantic_from_legacy
from .grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from .layout.candidates import select_layout
from .layout.models import LayoutResult
from .models import DrawingPlan, LegendItemPlan, LegendPlan
from .planner import plan_drawing
from .resolve import resolve_scene
from .scene import ResolvedScene
from .semantics.models import SemanticDiagram
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .validation import (
    DrawingCompilationError,
    DrawingDiagnostic,
    raise_for_errors,
    validate_canvas,
    validate_drawing_grammar,
    validate_drawing_semantics,
    validate_scene_accessibility,
    validate_scene_geometry,
    validate_scene_primitives,
)


def _layout_or_error(drawing: DrawingPlan, semantic: SemanticDiagram | None, grammar: ArchitectureGrammar) -> LayoutResult:
    try:
        return select_layout(drawing, semantic, grammar)
    except DrawingCompilationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise_for_errors("layout", (DrawingDiagnostic("ERROR", "LY000", str(exc)),))
        raise AssertionError("unreachable")


def _scene_or_error(
    drawing: DrawingPlan,
    layout: LayoutResult,
    grammar: ArchitectureGrammar,
    theme: FolioTheme,
) -> ResolvedScene:
    try:
        return resolve_scene(drawing, layout, grammar, theme)
    except DrawingCompilationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise_for_errors("scene", (DrawingDiagnostic("ERROR", "RS000", str(exc)),))
        raise AssertionError("unreachable")


def semantic_from_spec(spec: ArchitectureDiagramSpec) -> SemanticDiagram:
    return semantic_from_legacy(spec)


def drawing_plan_from_spec(
    spec: ArchitectureDiagramSpec,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> DrawingPlan:
    semantic = semantic_from_spec(spec)
    drawing = plan_drawing(semantic, grammar)
    legacy_nodes = {node.id: node for node in spec.nodes}
    legacy_archetypes = {"service": "component", "store": "datastore", "external": "external", "cloud": "cloud"}
    drawing = replace(
        drawing,
        language=spec.language or drawing.language,
        nodes=tuple(
            replace(
                node,
                archetype=legacy_archetypes[legacy_nodes[node.id].kind],
                content=replace(node.content, eyebrow=legacy_nodes[node.id].kind),
            )
            for node in drawing.nodes
        ),
    )
    if spec.legend:
        edge_channels = {"control": "primary-flow", "event": "async-flow", "async": "async-flow"}
        legend = LegendPlan("LEGEND", tuple(LegendItemPlan(edge_channels.get(item.flow, "secondary-flow"), item.label) for item in spec.legend))
        drawing = replace(drawing, legend=legend)
    else:
        drawing = replace(drawing, legend=None)
    return drawing


def compile_architecture(
    spec: ArchitectureDiagramSpec,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> tuple[SemanticDiagram, DrawingPlan, LayoutResult, ResolvedScene]:
    semantic = semantic_from_spec(spec)
    drawing = drawing_plan_from_spec(spec, grammar)
    raise_for_errors("plan", [*validate_drawing_semantics(drawing), *validate_drawing_grammar(drawing, grammar)])
    layout = _layout_or_error(drawing, semantic, grammar)
    raise_for_errors(
        "layout",
        [DrawingDiagnostic("ERROR", "LY001", item) for item in layout.warnings],
    )
    scene = _scene_or_error(drawing, layout, grammar, theme)
    raise_for_errors("scene", [
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene, grammar),
    ])
    return semantic, drawing, layout, scene


def compile_drawing_plan(
    drawing: DrawingPlan,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> tuple[LayoutResult, ResolvedScene]:
    raise_for_errors("plan", [*validate_drawing_semantics(drawing), *validate_drawing_grammar(drawing, grammar)])
    layout = _layout_or_error(drawing, None, grammar)
    raise_for_errors(
        "layout",
        [DrawingDiagnostic("ERROR", "LY001", item) for item in layout.warnings],
    )
    scene = _scene_or_error(drawing, layout, grammar, theme)
    raise_for_errors("scene", [
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene, grammar),
    ])
    return layout, scene
