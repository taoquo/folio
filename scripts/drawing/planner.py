from __future__ import annotations

from collections import Counter, defaultdict

from .grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from .models import (
    CompositionPlan,
    DrawingOverrides,
    DrawingPlan,
    HierarchyPlan,
    InformationBudget,
    LegendItemPlan,
    LegendPlan,
    NodeContentPlan,
    ReductionDecision,
    VisualEdgePlan,
    VisualNodePlan,
    VisualRegionPlan,
)
from .semantics.models import SemanticDiagram, SemanticEdge, SemanticNode
from .typography.measure import measure_text


def _archetype(node: SemanticNode) -> str:
    role = node.role.lower()
    if role in {"storage", "cache", "database", "warehouse"}:
        return "datastore"
    if role in {"entry", "client", "external", "resource-loader"}:
        return "external"
    if role in {"event-bus", "cloud"}:
        return "cloud"
    return "component"


def _channel(edge: SemanticEdge) -> str:
    if edge.relation in {"async", "event", "observe"} or edge.phase == "background":
        return "async-flow"
    if edge.importance in {"primary", "focal"}:
        return "primary-flow"
    return "secondary-flow"


def _size_tier(node: SemanticNode) -> str:
    title_width = measure_text(node.label, 12)
    metadata_width = measure_text(node.metadata or "", 9, "mono")
    if not node.metadata and title_width <= 104:
        return "compact"
    if title_width <= 140 and metadata_width <= 140:
        return "regular"
    return "wide"


def _pictogram(node: SemanticNode) -> str | None:
    role = node.role.lower()
    mapping = {
        "client": "client", "entry": "gateway", "gateway": "gateway",
        "event-bus": "queue", "queue": "queue", "database": "database",
        "warehouse": "database", "storage": "storage", "cache": "cache",
        "cloud": "cloud", "observability": "observability", "external": "external-system",
    }
    return mapping.get(role)


def _composition(semantic: SemanticDiagram) -> tuple[str, str, str]:
    if semantic.composition_hint:
        pattern = {
            "horizontal-layers": "layered",
            "vertical-stack": "pipeline",
            "hub-and-spoke": "hub",
        }.get(semantic.composition_hint, semantic.composition_hint)
        axis = "left-right" if pattern == "pipeline" else "top-down"
        return pattern, axis, "explicit composition hint preserved"
    degrees = Counter()
    for edge in semantic.edges:
        degrees[edge.source] += 1
        degrees[edge.target] += 1
    if degrees and max(degrees.values()) >= 4 and len(semantic.layer_order) <= 2:
        return "hub", "top-down", "single high-degree orchestration node detected"
    ordered_roles = {"event-bus", "executor", "storage", "warehouse", "entry"}
    if len(semantic.focus_path) >= 3 and {node.role for node in semantic.nodes}.issubset(ordered_roles):
        return "pipeline", "left-right", "ordered ingest-to-state focus path detected"
    return "layered", "top-down", f"{max(1, len(semantic.layer_order))} ordered semantic regions detected"


def _derive_spine(semantic: SemanticDiagram) -> tuple[str, ...]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in semantic.edges:
        outgoing[edge.source].append(edge.target)

    def walk(node_id: str, seen: tuple[str, ...]) -> tuple[str, ...]:
        candidates = [target for target in outgoing.get(node_id, ()) if target not in seen]
        if not candidates:
            return (*seen, node_id)
        paths = [walk(target, (*seen, node_id)) for target in candidates]
        return max(paths, key=lambda path: (len(path), tuple(reversed(path))))

    paths = [walk(node.id, ()) for node in semantic.nodes]
    return max(paths, key=lambda path: (len(path), tuple(reversed(path)))) if paths else ()


def _merge_recommendations(semantic: SemanticDiagram) -> list[ReductionDecision]:
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in semantic.edges:
        outgoing[edge.source].add(edge.target)
        incoming[edge.target].add(edge.source)
    decisions = []
    for index, left in enumerate(semantic.nodes):
        for right in semantic.nodes[index + 1:]:
            if left.role != right.role or left.domain != right.domain:
                continue
            left_signature = (incoming[left.id] - {right.id}, outgoing[left.id] - {right.id})
            right_signature = (incoming[right.id] - {left.id}, outgoing[right.id] - {left.id})
            if left_signature == right_signature and (left_signature[0] or left_signature[1]):
                decisions.append(
                    ReductionDecision(
                        "merge",
                        (left.id, right.id),
                        "same role, region, and external relationship signature",
                        False,
                    )
                )
    return decisions


def plan_drawing(
    semantic: SemanticDiagram,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    overrides: DrawingOverrides | None = None,
    budget: InformationBudget = InformationBudget(),
) -> DrawingPlan:
    pattern, axis, reason = _composition(semantic)
    focus = semantic.focus_candidates[0] if semantic.focus_candidates else (semantic.focus_path[0] if semantic.focus_path else None)
    if overrides and overrides.composition:
        pattern = overrides.composition
        axis = "left-right" if pattern == "pipeline" else "top-down"
        reason = "expert semantic composition override"
    if overrides and overrides.focus_node:
        focus = overrides.focus_node
    spine = overrides.spine if overrides and overrides.spine is not None else semantic.focus_path
    if pattern == "pipeline" and not spine:
        spine = _derive_spine(semantic)
    background = tuple(node.id for node in semantic.nodes if node.importance == "background" or node.role == "observability")
    layer_members: dict[str, list[str]] = defaultdict(list)
    for node in semantic.nodes:
        if node.domain:
            layer_members[node.domain].append(node.id)
    regions = [
        VisualRegionPlan(
            id=layer,
            role="layer",
            label=semantic.layer_labels.get(layer, layer.replace("-", " ").title()),
            members=tuple(layer_members.get(layer, ())),
            treatment="layer-band",
        )
        for layer in semantic.layer_order
        if layer_members.get(layer)
    ]
    regions.extend(
        VisualRegionPlan(group.id, group.role or "group", group.label, group.members, "soft-boundary")
        for group in semantic.groups
    )
    if overrides and overrides.node_order:
        regions = [
            VisualRegionPlan(region.id, region.role, region.label, overrides.node_order.get(region.id, region.members), region.treatment)
            for region in regions
        ]
    nodes = tuple(
        VisualNodePlan(
            id=node.id,
            archetype=_archetype(node),
            emphasis="focal" if node.id == focus else ("background" if node.id in background else "normal"),
            region=node.domain,
            content=NodeContentPlan(_archetype(node), node.label, node.metadata, node.description),
            size_tier=_size_tier(node),
            pictogram=_pictogram(node),
        )
        for node in semantic.nodes
    )
    focus_pairs = set(zip(spine, spine[1:]))
    raw_edges = tuple(
        VisualEdgePlan(
            id=edge.id,
            source=edge.source,
            target=edge.target,
            channel=_channel(edge),
            emphasis="focal" if (edge.source, edge.target) in focus_pairs else ("background" if edge.importance == "background" else "normal"),
            label=edge.label,
        )
        for edge in semantic.edges
    )
    labelled = 0
    dropped_labels = 0
    edges_list = []
    # V5: the label budget is both absolute (max_edge_labels) and relative.
    # diagnose_taste flags DG118 above 75% labelled edges, so honour the same ceiling here
    # instead of emitting a plan the taste gate is guaranteed to reject.
    label_ceiling = min(budget.max_edge_labels, int(len(raw_edges) * 0.75)) if raw_edges else 0
    for edge in raw_edges:
        label = edge.label
        if label:
            if labelled >= label_ceiling and edge.emphasis != "focal":
                label = None
                dropped_labels += 1
            else:
                labelled += 1
        edges_list.append(
            VisualEdgePlan(
                edge.id,
                edge.source,
                edge.target,
                edge.channel,
                edge.emphasis,
                label,
                edge.direction,
                edge.route_policy,
            )
        )
    edges = tuple(edges_list)
    sidecars: dict[str, tuple[str, ...]] = {}
    if focus:
        supporting = tuple(node.id for node in semantic.nodes if node.id in background)
        if supporting:
            sidecars[focus] = supporting
    legend_items = tuple(
        LegendItemPlan(channel, channel.replace("-flow", "").replace("-", " ").title())
        for channel in dict.fromkeys(edge.channel for edge in edges)
    )
    legend = LegendPlan("LEGEND", legend_items) if len(legend_items) > 1 else None
    reductions = _merge_recommendations(semantic)
    explanation = [
        f"composition: {pattern}; reason: {reason}",
        f"focus: {focus or 'none'}; reason: highest narrative priority candidate",
        f"spine: {' -> '.join(spine) if spine else 'none'}; reason: selected semantic focus path",
        f"background: {', '.join(background) if background else 'none'}; reason: supporting concern outside primary narrative",
        f"nodes: {len(nodes)}; reason: semantic roles mapped to {len(set(node.archetype for node in nodes))} visual archetypes",
        f"edges: {len(edges)}; reason: relations mapped to primary, secondary, or async channels",
    ]
    if dropped_labels:
        dropped_ids = tuple(edge.id for edge, resolved in zip(raw_edges, edges) if edge.label and not resolved.label)
        reason = f"edge-label budget is {label_ceiling}"
        reductions.append(ReductionDecision("drop", dropped_ids, reason, True))
        explanation.append(f"reduction: drop {dropped_labels} secondary edge labels; reason: {reason}")
    if len(nodes) > 9:
        reductions.append(ReductionDecision("split", tuple(node.id for node in nodes), "visual node budget is 9", False))
        explanation.append(f"reduction: split recommended; reason: {len(nodes)} visual nodes exceed budget 9")
    if background:
        reductions.append(ReductionDecision("background", background, "supporting concern outside primary narrative", True))
        explanation.append(f"reduction: background {len(background)} supporting nodes; reason: preserve context without competing with focus")
    for decision in reductions:
        if decision.action == "merge":
            explanation.append(f"reduction: merge recommended for {', '.join(decision.targets)}; reason: {decision.reason}")
    return DrawingPlan(
        kind="architecture",
        title=semantic.title,
        composition=CompositionPlan(pattern, axis, "restrained", spine, sidecars),
        hierarchy=HierarchyPlan(focus, spine, background),
        regions=tuple(regions),
        nodes=nodes,
        edges=edges,
        legend=legend,
        width=semantic.width,
        height=semantic.height,
        subtitle=semantic.subtitle,
        caption=semantic.caption,
        explanation=tuple(explanation),
        reductions=tuple(reductions),
        language="zh" if any("\u4e00" <= char <= "\u9fff" for char in semantic.title + "".join(node.label for node in semantic.nodes)) else "en",
    )
