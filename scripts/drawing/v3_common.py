"""Compatibility surface for the modules that still import from the old shared file.

The name came from the fixture generation that first needed these helpers, and it stopped
describing the contents once v4 notation and v5 schematic families started importing the same
utilities. Worse, it mixed two unrelated layers: payload checks that all twenty-three kinds
need, and a graph layout engine that only the four structural kinds use, which meant a chart
family importing a validator also inherited a router it had no use for.

The pieces now live where they belong:

* :mod:`drawing.validation.payload` -- identifier, field and edge checks, all kinds
* :mod:`drawing.typography.text` -- language inference, wrapping, canvas sizing, all kinds
* :mod:`drawing.layout.layered_graph` -- banded layout and routing, structural kinds only
* :mod:`drawing.layout.grid` -- the 4-unit snap

This module re-exports them so existing call sites keep working. Import from the modules above
in new code; nothing new should reference a version number that no longer means anything.
"""

from __future__ import annotations

from .layout.layered_graph import (
    GraphComposition,
    GraphEdgePlan,
    GraphNodePlan,
    GraphPlan,
    arrow_for,
    fit_layered_graph_height,
    graph_band_top,
    graph_depths,
    graph_has_feedback,
    layout_layered_graph,
    layout_result,
    node_size,
    plan_node_size,
    resolve_graph_scene,
    route_graph_edges,
)
from .typography.text import dimensions, infer_language, wrap_text
from .validation.payload import (
    common_payload_diagnostics,
    cycle_exists,
    edge_label_signature,
    finite_number,
    object_list,
    reachable,
    require_no_errors,
    validate_distinguishable_parallel_edges,
    validate_item_strings,
    validate_no_self_edges,
    validate_object_fields,
    validate_resolved_scene,
    validate_unique_ids,
)

__all__ = [
    "GraphComposition", "GraphEdgePlan", "GraphNodePlan", "GraphPlan", "arrow_for",
    "common_payload_diagnostics", "cycle_exists", "dimensions", "edge_label_signature",
    "finite_number", "fit_layered_graph_height", "graph_band_top", "graph_depths",
    "graph_has_feedback", "infer_language", "layout_layered_graph", "layout_result",
    "node_size", "object_list", "plan_node_size", "reachable", "require_no_errors",
    "resolve_graph_scene", "route_graph_edges", "validate_distinguishable_parallel_edges",
    "validate_item_strings", "validate_no_self_edges", "validate_object_fields",
    "validate_resolved_scene", "validate_unique_ids", "wrap_text",
]
