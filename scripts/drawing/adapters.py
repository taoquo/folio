from __future__ import annotations

from diagram_models import ArchitectureDiagramSpec, load_diagram_spec

from .layout.models import LayoutConstraintSet
from .models import DrawingPlan
from .semantics.models import SemanticDiagram, SemanticEdge, SemanticGroup, SemanticNode


def semantic_from_legacy(spec: ArchitectureDiagramSpec) -> SemanticDiagram:
    nodes = tuple(
        SemanticNode(
            id=node.id,
            label=node.label,
            role=node.role or node.kind,
            description=node.description,
            importance=node.importance or "normal",
            state_owner=bool(node.state_owner),
            lifecycle_phase=node.lifecycle_phase,
            domain=node.layer,
            metadata=node.sublabel,
        )
        for node in spec.nodes
    )
    edges = tuple(
        SemanticEdge(
            id=f"edge:{index}:{edge.source}->{edge.target}",
            source=edge.source,
            target=edge.target,
            relation=edge.flow or edge.interaction or edge.kind,
            interaction=edge.interaction,
            importance=edge.priority or edge.kind,
            phase=edge.phase,
            label=edge.label,
        )
        for index, edge in enumerate(spec.edges)
    )
    groups = tuple(SemanticGroup(group.id, group.label, tuple(group.members), group.kind, group.layer) for group in spec.groups)
    return SemanticDiagram(
        title=spec.title,
        nodes=nodes,
        edges=edges,
        groups=groups,
        focus_candidates=(spec.focus,) if spec.focus else (),
        focus_path=tuple(spec.focus_path),
        narrative=spec.focus_reason,
        width=spec.width,
        height=spec.height,
        subtitle=spec.subtitle,
        caption=spec.caption,
        layer_order=tuple(layer.id for layer in spec.layers),
        layer_labels={layer.id: layer.label for layer in spec.layers},
        composition_hint=spec.layout,
    )


def _old_node_kind(archetype: str) -> str:
    return {"component": "service", "datastore": "store", "external": "external", "cloud": "cloud"}[archetype]


def _old_edge_kind(channel: str) -> str:
    return {"primary-flow": "primary", "secondary-flow": "secondary", "async-flow": "async"}[channel]


def drawing_to_legacy(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    semantic: SemanticDiagram | None = None,
) -> ArchitectureDiagramSpec:
    semantic_nodes = {node.id: node for node in semantic.nodes} if semantic else {}
    semantic_edges = {edge.id: edge for edge in semantic.edges} if semantic else {}
    layer_regions = [region for region in drawing.regions if region.treatment == "layer-band"]
    group_regions = [region for region in drawing.regions if region.treatment == "soft-boundary"]
    payload = {
        "kind": "architecture",
        "title": drawing.title,
        "layout": "horizontal-layers" if drawing.composition.pattern == "layered" else "vertical-stack",
        "width": drawing.width,
        "height": drawing.height,
        "subtitle": drawing.subtitle,
        "caption": drawing.caption,
        "focus": drawing.hierarchy.focus_node,
        "focus_path": list(drawing.hierarchy.focus_path),
        "focus_reason": semantic.narrative if semantic else None,
        "layers": [{"id": region.id, "label": region.label, "order": index + 1} for index, region in enumerate(layer_regions)],
        "groups": [
            {"id": region.id, "label": region.label, "kind": region.role, "members": list(region.members)}
            for region in group_regions
        ],
        "nodes": [],
        "edges": [],
        "legend": [
            {"flow": item.channel, "label": item.label}
            for item in (drawing.legend.items if drawing.legend else ())
        ],
    }
    for node in drawing.nodes:
        source = semantic_nodes.get(node.id)
        payload["nodes"].append(
            {
                "id": node.id,
                "kind": _old_node_kind(node.archetype),
                "label": node.content.title,
                "layer": node.region,
                "sublabel": node.content.metadata,
                "role": source.role if source else None,
                "description": node.content.description,
                "importance": source.importance if source and source.importance in {"primary", "secondary", "background"} else None,
                "state_owner": source.state_owner if source else None,
                "lifecycle_phase": source.lifecycle_phase if source else None,
            }
        )
    for edge in drawing.edges:
        source = semantic_edges.get(edge.id)
        ports = constraints.port_preferences[edge.id]
        payload["edges"].append(
            {
                "source": edge.source,
                "target": edge.target,
                "kind": _old_edge_kind(edge.channel),
                "label": edge.label,
                "flow": source.relation if source else edge.channel,
                "interaction": source.interaction if source else None,
                "priority": "primary" if edge.emphasis == "focal" else "background" if edge.emphasis == "background" else None,
                "dashed": edge.channel == "async-flow",
                "source_port": ports.source,
                "target_port": ports.target,
                "phase": source.phase if source else None,
            }
        )
    return load_diagram_spec(payload)
