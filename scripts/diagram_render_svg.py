from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec


PARCHMENT = "#F6F0EA"
IVORY = "#FBF7F3"
NEAR_BLACK = "#191514"
OLIVE = "#5A4A43"
STONE = "#85776F"
BRAND = "#B83D2E"
BRAND_TINT = "#F7E6E1"
BORDER = "#E9DED4"


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


def render_diagram_svg(spec: DiagramSpec) -> str:
    if getattr(spec, "kind", None) == "architecture":
        return render_architecture_svg(spec)
    if getattr(spec, "kind", None) == "uml-class":
        return render_uml_class_svg(spec)
    raise TypeError(f"unsupported spec type: {type(spec)!r}")


def render_architecture_svg(spec: ArchitectureDiagramSpec) -> str:
    boxes = _center_architecture_boxes(spec, _architecture_boxes(spec))
    focus_pairs = {
        (spec.focus_path[index], spec.focus_path[index + 1])
        for index in range(len(spec.focus_path) - 1)
    }
    edge_fragments = []
    group_fragments = _architecture_group_fragments(spec, boxes)
    for edge in spec.edges:
        start = boxes[edge.source]
        end = boxes[edge.target]
        points = _route_architecture_edge(start, end, edge.source_port, edge.target_port, edge.route_hint)
        stroke, stroke_width = _edge_style(edge.kind, edge.priority, (edge.source, edge.target) in focus_pairs)
        classes = ["arch-edge", f"arch-edge--{edge.kind}"]
        if (edge.source, edge.target) in focus_pairs:
            classes.append("arch-edge--focus")
        dash = ' stroke-dasharray="5 4"' if edge.dashed or edge.kind == "async" else ""
        edge_fragments.append(
            f'<path class="{" ".join(classes)}" d="{_path_from_points(points)}" fill="none" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"{dash} />'
        )
        edge_fragments.append(_chevron_for_segment(points[-2], points[-1], stroke, stroke_width=stroke_width))
        if edge.label:
            label_x, label_y = _label_point(points)
            label_tier, label_fill, label_font_size, label_bg_opacity = _edge_label_style(
                edge.kind,
                edge.priority,
                (edge.source, edge.target) in focus_pairs,
            )
            label_width = max(42, len(edge.label) * 7 + 12)
            edge_fragments.append(
                f'<rect class="arch-edge-label-bg arch-edge-label-bg--{label_tier}" '
                f'x="{label_x - label_width // 2}" y="{label_y - 18}" width="{label_width}" height="12" '
                f'rx="2" fill="{PARCHMENT}" fill-opacity="{label_bg_opacity}" />'
            )
            edge_fragments.append(
                f'<text class="arch-edge-label arch-edge-label--{label_tier}" '
                f'x="{label_x}" y="{label_y - 9}" fill="{label_fill}" font-size="{label_font_size}" '
                'font-family="\'JetBrains Mono\', monospace" text-anchor="middle">'
                f"{escape(edge.label)}</text>"
            )

    node_fragments = []
    layer_fragments = []
    legend_fragments = _architecture_legend_fragments(spec)
    if spec.layout == "horizontal-layers" and spec.layers:
        rows = _architecture_layer_rows(spec, boxes)
        for layer, (top, bottom) in rows:
            center_y = (top + bottom) // 2
            layer_fragments.append(
                f'<text x="32" y="{center_y}" fill="{STONE}" font-size="11" '
                'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.08em">'
                f"{escape(layer.label.upper())}</text>"
            )
            layer_fragments.append(
                f'<line x1="70" y1="{bottom + 18}" x2="{spec.width - 40}" y2="{bottom + 18}" stroke="{BORDER}" stroke-width="1" />'
            )

    for node in spec.nodes:
        box = boxes[node.id]
        is_focus = node.id == spec.focus
        fill = BRAND_TINT if is_focus else IVORY
        stroke = BRAND if is_focus else _node_stroke(node.kind)
        kind_fill = BRAND if is_focus else STONE
        node_fragments.append(
            f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1" />'
        )
        node_fragments.append(
            f'<text x="{box.x + 18}" y="{box.y + 18}" fill="{kind_fill}" font-size="7" '
            'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.15em">'
            f"{escape(node.kind.upper())}</text>"
        )
        node_fragments.append(
            f'<text x="{box.x + box.w // 2}" y="{box.y + 38}" fill="{NEAR_BLACK}" font-size="12" '
            'font-family="Charter, Georgia, serif" font-weight="600" text-anchor="middle">'
            f"{escape(node.label)}</text>"
        )
        if node.sublabel:
            node_fragments.append(
                f'<text x="{box.x + box.w // 2}" y="{box.y + 54}" fill="{OLIVE}" font-size="9" '
                'font-family="\'JetBrains Mono\', monospace" text-anchor="middle">'
                f"{escape(node.sublabel)}</text>"
            )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">'
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />'
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>"
        f'{"".join(layer_fragments)}{"".join(group_fragments)}{"".join(edge_fragments)}'
        f'{"".join(node_fragments)}{"".join(legend_fragments)}</svg>'
    )


def render_uml_class_svg(spec: UmlClassDiagramSpec) -> str:
    boxes = _uml_boxes(spec)
    source_side_counts: dict[tuple[str, str], int] = {}
    target_side_counts: dict[tuple[str, str], int] = {}
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />',
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>",
    ]
    relation_fragments = []
    for relation in spec.relationships:
        source = boxes[relation.source]
        target = boxes[relation.target]
        source_side, target_side = _uml_sides(source, target)
        source_key = (relation.source, source_side)
        target_key = (relation.target, target_side)
        source_slot = source_side_counts.get(source_key, 0)
        target_slot = target_side_counts.get(target_key, 0)
        source_side_counts[source_key] = source_slot + 1
        target_side_counts[target_key] = target_slot + 1
        start, end = _uml_anchors(source, target, source_side, target_side, source_slot, target_slot)
        line_start, line_end = start, end
        if relation.kind in {"aggregation", "composition"}:
            diamond, line_start = _diamond_at_point(start, end, filled=relation.kind == "composition")
            relation_fragments.append(diamond)
        if relation.kind == "inheritance":
            triangle, line_end = _triangle_at_point(end, start)
            relation_fragments.append(triangle)

        path_points = _uml_route_points(
            line_start,
            line_end,
            source,
            target,
            source_side,
            target_side,
            boxes,
            relation.source,
            relation.target,
            relation.route_policy,
        )
        relation_fragments.append(
            f'<path class="uml-edge" d="{_path_from_points(path_points)}" fill="none" stroke="{OLIVE}" stroke-width="1.2" />'
        )
        if relation.kind == "association":
            relation_fragments.append(_chevron_for_segment(path_points[-2], path_points[-1], OLIVE, klass="uml-edge-head"))
        if relation.label:
            label_x, label_y = _uml_label_point(path_points, relation.label_lane, relation.label_offset)
            relation_fragments.append(
                f'<text x="{label_x}" y="{label_y - 8}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace" text-anchor="middle">{escape(relation.label)}</text>'
            )
        if relation.source_multiplicity:
            relation_fragments.append(
                f'<text x="{line_start[0] - 10}" y="{line_start[1] - 6}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace" text-anchor="end">{escape(relation.source_multiplicity)}</text>'
            )
        if relation.target_multiplicity:
            relation_fragments.append(
                f'<text x="{line_end[0] + 10}" y="{line_end[1] - 6}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace">{escape(relation.target_multiplicity)}</text>'
            )

    fragments.extend(relation_fragments)

    for item in spec.types:
        x, y = boxes[item.id].x, boxes[item.id].y
        body_h = 62 + 18 * len(item.attributes) + 18 * len(item.methods)
        stroke = BRAND if item.id == spec.focus else NEAR_BLACK
        fragments.append(
            f'<rect x="{x}" y="{y}" width="220" height="{body_h}" rx="6" fill="{IVORY}" stroke="{stroke}" stroke-width="1" />'
        )
        fragments.append(
            f'<line x1="{x}" y1="{y + 34}" x2="{x + 220}" y2="{y + 34}" stroke="{BORDER}" stroke-width="1" />'
        )
        attr_divider_y = y + 52 + 18 * max(1, len(item.attributes))
        fragments.append(
            f'<line x1="{x}" y1="{attr_divider_y}" x2="{x + 220}" y2="{attr_divider_y}" stroke="{BORDER}" stroke-width="1" />'
        )
        fragments.append(
            f'<text x="{x + 110}" y="{y + 22}" fill="{NEAR_BLACK}" font-size="13" '
            'font-family="Charter, Georgia, serif" font-weight="600" text-anchor="middle">'
            f"{escape(item.name)}</text>"
        )
        attr_y = y + 52
        for attr in item.attributes:
            fragments.append(
                f'<text x="{x + 12}" y="{attr_y}" fill="{OLIVE}" font-size="10" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(attr)}</text>"
            )
            attr_y += 18
        method_y = attr_divider_y + 18
        for method in item.methods:
            fragments.append(
                f'<text x="{x + 12}" y="{method_y}" fill="{NEAR_BLACK}" font-size="10" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(method)}</text>"
            )
            method_y += 18
    fragments.append("</svg>")
    return "".join(fragments)


def _architecture_boxes(spec: ArchitectureDiagramSpec) -> dict[str, Box]:
    if spec.layout == "vertical-stack":
        y = 100
        boxes = {}
        for node in spec.nodes:
            boxes[node.id] = Box(320, y, 320, 64)
            y += 96
        return boxes

    if spec.layout == "hub-and-spoke":
        positions = [(380, 210), (120, 80), (640, 80), (120, 340), (640, 340)]
        boxes = {}
        for index, node in enumerate(spec.nodes):
            x, y = positions[min(index, len(positions) - 1)]
            boxes[node.id] = Box(x, y, 200, 64)
        return boxes

    rows = _architecture_rows(spec)
    boxes = {}
    row_gap = 118
    start_y = 96
    desired_centers = _architecture_desired_centers(spec, rows)
    for row_index, (layer_id, row_nodes) in enumerate(rows):
        if not row_nodes:
            continue
        y = start_y + row_index * row_gap
        row_policy = _resolve_row_policy(spec, layer_id, row_nodes, desired_centers)
        for node, x in _architecture_row_layout(spec.width, row_nodes, desired_centers, row_policy):
            boxes[node.id] = Box(x, y, 160, 64)
    return boxes


def _route_architecture_edge(
    start: Box,
    end: Box,
    source_port: str | None = None,
    target_port: str | None = None,
    route_hint: str | None = None,
) -> list[tuple[int, int]]:
    start_side = _normalize_port(source_port, start, end)
    end_side = _normalize_port(target_port, end, start)
    start_point = _box_side_anchor(start, start_side)
    end_point = _box_side_anchor(end, end_side)

    if route_hint == "straight":
        if start_point[0] == end_point[0] or start_point[1] == end_point[1]:
            return [start_point, end_point]
        return [start_point, (end_point[0], start_point[1]), end_point]

    if route_hint == "drop_to_lower_layer":
        corridor_y = start_point[1] + max(22, abs(end_point[1] - start_point[1]) // 3)
        return [start_point, (start_point[0], corridor_y), (end_point[0], corridor_y), end_point]

    if route_hint == "rise_to_upper_layer":
        corridor_y = start_point[1] - max(22, abs(end_point[1] - start_point[1]) // 3)
        return [start_point, (start_point[0], corridor_y), (end_point[0], corridor_y), end_point]

    same_row = abs(start.y - end.y) < 8
    if same_row:
        return [start_point, end_point]

    corridor_y = (start_point[1] + end_point[1]) // 2
    return [start_point, (start_point[0], corridor_y), (end_point[0], corridor_y), end_point]


def _architecture_layer_rows(spec: ArchitectureDiagramSpec, boxes: dict[str, Box]) -> list[tuple[object, tuple[int, int]]]:
    rows = []
    for layer in spec.layers:
        layer_boxes = [boxes[node.id] for node in spec.nodes if node.layer == layer.id and node.id in boxes]
        if not layer_boxes:
            continue
        top = min(box.y for box in layer_boxes)
        bottom = max(box.y + box.h for box in layer_boxes)
        rows.append((layer, (top, bottom)))
    return rows


def _architecture_group_fragments(spec: ArchitectureDiagramSpec, boxes: dict[str, Box]) -> list[str]:
    fragments = []
    for group in spec.groups:
        group_boxes = [boxes[member] for member in group.members if member in boxes]
        if len(group_boxes) < 2:
            continue
        left = min(box.x for box in group_boxes) - 18
        top = min(box.y for box in group_boxes) - 24
        right = max(box.x + box.w for box in group_boxes) + 18
        bottom = max(box.y + box.h for box in group_boxes) + 18
        width = right - left
        height = bottom - top
        fragments.append(
            f'<rect class="arch-group" x="{left}" y="{top}" width="{width}" height="{height}" rx="10" '
            f'fill="{IVORY}" fill-opacity="0.28" stroke="{BORDER}" stroke-width="1" stroke-dasharray="5 4" />'
        )
        fragments.append(
            f'<text x="{left + 14}" y="{top + 16}" fill="{STONE}" font-size="8" '
            'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.12em">'
            f"{escape(group.label.upper())}</text>"
        )
    return fragments


def _architecture_rows(spec: ArchitectureDiagramSpec) -> list[tuple[str, list[object]]]:
    rows: list[tuple[str, list[object]]] = []
    layer_order = [layer.id for layer in spec.layers]
    if layer_order:
        for layer_id in layer_order:
            rows.append((layer_id, [node for node in spec.nodes if node.layer == layer_id]))
        unlayered = [node for node in spec.nodes if node.layer not in layer_order]
        if unlayered:
            rows.append(("unlayered", unlayered))
        return rows
    return [("default", list(spec.nodes))]


def _architecture_content_bounds(boxes: dict[str, Box]) -> tuple[int, int, int, int]:
    if not boxes:
        return (0, 0, 0, 0)
    left = min(box.x for box in boxes.values())
    top = min(box.y for box in boxes.values())
    right = max(box.x + box.w for box in boxes.values())
    bottom = max(box.y + box.h for box in boxes.values())
    return (left, top, right, bottom)


def _center_architecture_boxes(spec: ArchitectureDiagramSpec, boxes: dict[str, Box]) -> dict[str, Box]:
    if not boxes:
        return boxes
    left, top, right, bottom = _architecture_content_bounds(boxes)
    legend_metrics = _architecture_legend_metrics(spec)
    stage_left = 160
    stage_right = spec.width - 40
    stage_top = 80
    stage_bottom = legend_metrics["y"] - 24 if legend_metrics else spec.height - 48
    target_center_x = (stage_left + stage_right) // 2
    target_center_y = (stage_top + stage_bottom) // 2
    current_center_x = (left + right) // 2
    current_center_y = (top + bottom) // 2
    shift_x = target_center_x - current_center_x
    shift_y = target_center_y - current_center_y
    shifted_left = left + shift_x
    shifted_right = right + shift_x
    shifted_top = top + shift_y
    shifted_bottom = bottom + shift_y
    if shifted_left < stage_left:
        shift_x += stage_left - shifted_left
    if shifted_right > stage_right:
        shift_x -= shifted_right - stage_right
    if shifted_top < stage_top:
        shift_y += stage_top - shifted_top
    if shifted_bottom > stage_bottom:
        shift_y -= shifted_bottom - stage_bottom
    return {
        node_id: Box(box.x + shift_x, box.y + shift_y, box.w, box.h)
        for node_id, box in boxes.items()
    }


def _architecture_desired_centers(
    spec: ArchitectureDiagramSpec,
    rows: list[tuple[str, list[object]]],
) -> dict[str, int]:
    step = 200
    spine = spec.width // 2
    focus_index = {node_id: index for index, node_id in enumerate(spec.focus_path)}
    row_by_node = {
        node.id: layer_id
        for layer_id, row_nodes in rows
        for node in row_nodes
    }
    desired: dict[str, int] = {}

    for _layer_id, row_nodes in rows:
        row_focus = [node for node in row_nodes if node.id in focus_index]
        if not row_focus:
            continue
        row_focus.sort(key=lambda node: focus_index[node.id])
        centers = _centers_around_spine(spine, len(row_focus), step)
        for node, center in zip(row_focus, centers):
            desired[node.id] = center

    for group in spec.groups:
        row_members = [member for member in group.members if member in row_by_node]
        if len(row_members) < 2:
            continue
        if any(member in desired for member in row_members):
            continue
        layout_policy = _resolve_group_layout_policy(group, spec.focus_path)
        centers = _group_centers_for_policy(layout_policy, spine, len(row_members), step)
        for member, center in zip(row_members, centers):
            desired[member] = center

    edges = sorted(
        spec.edges,
        key=lambda edge: (_edge_priority_rank(edge.priority, edge.kind), 0 if edge.kind == "primary" else 1),
        reverse=True,
    )
    for _ in range(3):
        changed = False
        for edge in edges:
            source_known = edge.source in desired
            target_known = edge.target in desired
            same_row = row_by_node.get(edge.source) == row_by_node.get(edge.target)
            attachment_policy = _resolve_attachment_policy(edge, same_row)
            if source_known and not target_known:
                desired[edge.target] = _propagate_edge_center(
                    desired[edge.source],
                    edge,
                    attachment_policy,
                    from_source=True,
                    step=step,
                )
                changed = True
            elif target_known and not source_known:
                desired[edge.source] = _propagate_edge_center(
                    desired[edge.target],
                    edge,
                    attachment_policy,
                    from_source=False,
                    step=step,
                )
                changed = True
        if not changed:
            break

    return desired


def _architecture_row_layout(
    diagram_width: int,
    row_nodes: list[object],
    desired_centers: dict[str, int],
    row_policy: str,
) -> list[tuple[object, int]]:
    width = 160
    gap = 40
    step = width + gap
    min_x = 84
    max_x = diagram_width - min_x - width

    anchored_nodes = [node for node in row_nodes if node.id in desired_centers]
    if not anchored_nodes:
        ordered_nodes = _row_policy_order(row_policy, row_nodes)
        return _default_row_layout(diagram_width, ordered_nodes, width, gap)

    anchored_nodes.sort(key=lambda node: desired_centers[node.id])
    anchored_xs = [
        max(min_x, min(desired_centers[node.id] - width // 2, max_x))
        for node in anchored_nodes
    ]
    anchored_xs = _spread_positions(anchored_xs, min_x, max_x, step)
    unassigned_count = len(row_nodes) - len(anchored_nodes)
    if unassigned_count and anchored_xs:
        available_right = max_x - anchored_xs[-1]
        needed_right = step * unassigned_count
        required_shift = max(0, needed_right - available_right)
        max_shift = anchored_xs[0] - min_x
        if required_shift and max_shift > 0:
            shift = min(required_shift, max_shift)
            anchored_xs = [x - shift for x in anchored_xs]
    placements = {
        node.id: x
        for node, x in zip(anchored_nodes, anchored_xs)
    }

    policy_order = _row_policy_order(row_policy, [node for node in row_nodes if node.id not in placements])
    right_cursor = max(anchored_xs) + step
    left_cursor = min(anchored_xs) - step
    prefer_right = True
    for node in policy_order:
        candidate = right_cursor if prefer_right else left_cursor
        if candidate > max_x:
            candidate = left_cursor
            left_cursor -= step
        elif candidate < min_x:
            candidate = right_cursor
            right_cursor += step
        else:
            if prefer_right:
                right_cursor += step
            else:
                left_cursor -= step
        placements[node.id] = max(min_x, min(candidate, max_x))
        prefer_right = row_policy != "centered"

    ordered_nodes = sorted(row_nodes, key=lambda node: placements[node.id])
    return [(node, placements[node.id]) for node in ordered_nodes]


def _default_row_layout(
    diagram_width: int,
    row_nodes: list[object],
    width: int,
    gap: int,
) -> list[tuple[object, int]]:
    count = len(row_nodes)
    total = count * width + (count - 1) * gap
    x = max(84, (diagram_width - total) // 2)
    positioned = []
    for node in row_nodes:
        positioned.append((node, x))
        x += width + gap
    return positioned


def _focus_centers(diagram_width: int, count: int, step: int) -> list[int]:
    spine = diagram_width // 2
    return _centers_around_spine(spine, count, step)


def _centers_around_spine(spine: int, count: int, step: int) -> list[int]:
    if count == 1:
        return [spine]
    start = spine - ((count - 1) * step) // 2
    return [start + index * step for index in range(count)]


def _architecture_legend_metrics(spec: ArchitectureDiagramSpec) -> dict[str, object] | None:
    if not spec.legend:
        return None
    title_width = 64
    item_gap = 28
    items = []
    total_width = 14 + title_width + 18
    for item in spec.legend:
        item_width = 20 + 8 + len(item.label) * 7
        items.append({"flow": item.flow, "label": item.label, "width": item_width})
        total_width += item_width
    total_width += item_gap * max(0, len(items) - 1) + 14
    width = max(260, total_width)
    height = 42
    x = (spec.width - width) // 2
    y = spec.height - 58
    cursor_x = x + 14 + title_width + 6
    baseline_y = y + 25
    laid_out = []
    for index, item in enumerate(items):
        if index:
            cursor_x += item_gap
        laid_out.append(
            {
                "flow": item["flow"],
                "label": item["label"],
                "x": cursor_x,
                "text_x": cursor_x + 28,
                "y": baseline_y,
            }
        )
        cursor_x += item["width"]
    return {"x": x, "y": y, "width": width, "height": height, "items": laid_out}


def _edge_priority_rank(priority: str | None, kind: str) -> int:
    if priority == "primary" or kind == "primary":
        return 3
    if priority == "secondary":
        return 2
    if priority == "background":
        return 1
    return 2 if kind == "secondary" else 1


def _propagate_edge_center(
    anchor_center: int,
    edge: object,
    attachment_policy: str,
    from_source: bool,
    step: int,
) -> int:
    if attachment_policy == "align-column":
        return anchor_center

    if attachment_policy == "attach-right":
        return anchor_center + step if from_source else anchor_center - step

    if attachment_policy == "attach-left":
        return anchor_center - step if from_source else anchor_center + step

    return anchor_center + step if from_source else anchor_center - step


def _row_policy_order(row_policy: str, row_nodes: list[object]) -> list[object]:
    def importance_rank(node: object) -> int:
        return {
            "primary": 0,
            "secondary": 1,
            "background": 2,
            None: 1,
        }.get(getattr(node, "importance", None), 1)

    if row_policy == "attachments-right":
        return sorted(row_nodes, key=lambda node: (importance_rank(node), getattr(node, "kind", ""), node.id))
    if row_policy == "pipeline":
        return sorted(row_nodes, key=lambda node: (importance_rank(node), node.id))
    return sorted(row_nodes, key=lambda node: (importance_rank(node), getattr(node, "kind", ""), node.id))


def _spread_positions(xs: list[int], min_x: int, max_x: int, step: int) -> list[int]:
    if not xs:
        return xs
    spread = [max(min_x, min(xs[0], max_x))]
    for x in xs[1:]:
        spread.append(max(x, spread[-1] + step))
    overflow = spread[-1] - max_x
    if overflow > 0:
        spread = [x - overflow for x in spread]
        if spread[0] < min_x:
            shift = min_x - spread[0]
            spread = [x + shift for x in spread]
    return spread


def _resolve_group_layout_policy(group: object, focus_path: list[str]) -> str:
    if getattr(group, "layout_policy", None):
        return group.layout_policy
    shared_focus = [member for member in group.members if member in focus_path]
    if group.kind == "runtime-loop" or len(shared_focus) >= 2:
        return "pipeline"
    return "center-band"


def _group_centers_for_policy(layout_policy: str, spine: int, count: int, step: int) -> list[int]:
    if layout_policy == "sidecar":
        start = spine + step // 2
        return [start + index * step for index in range(count)]
    if layout_policy == "stack":
        return [spine for _ in range(count)]
    return _centers_around_spine(spine, count, step)


def _resolve_row_policy(
    spec: ArchitectureDiagramSpec,
    layer_id: str,
    row_nodes: list[object],
    desired_centers: dict[str, int],
) -> str:
    for layer in spec.layers:
        if layer.id == layer_id and layer.row_policy:
            return layer.row_policy
    anchored = [node for node in row_nodes if node.id in desired_centers]
    if len(anchored) > 1:
        return "pipeline"
    if anchored:
        return "attachments-right"
    return "centered"


def _resolve_attachment_policy(edge: object, same_row: bool) -> str:
    if not same_row:
        return "align-column"
    if edge.target_port == "left" or edge.source_port == "right":
        return "attach-right"
    if edge.target_port == "right" or edge.source_port == "left":
        return "attach-left"
    return "attach-right"


def _architecture_legend_fragments(spec: ArchitectureDiagramSpec) -> list[str]:
    metrics = _architecture_legend_metrics(spec)
    if metrics is None:
        return []
    fragments = [
        f'<rect class="arch-legend" x="{metrics["x"]}" y="{metrics["y"]}" width="{metrics["width"]}" height="{metrics["height"]}" rx="8" fill="{IVORY}" stroke="{BORDER}" stroke-width="1" />',
        f'<text x="{metrics["x"] + 14}" y="{metrics["y"] + 16}" fill="{STONE}" font-size="8" font-family="\'JetBrains Mono\', monospace" letter-spacing="0.12em">LEGEND</text>',
    ]
    for item in metrics["items"]:
        sample_color = _legend_flow_color(item["flow"])
        row_y = item["y"]
        fragments.append(
            f'<line x1="{item["x"]}" y1="{row_y}" x2="{item["x"] + 20}" y2="{row_y}" stroke="{sample_color}" stroke-width="1.6" />'
        )
        fragments.append(
            f'<text x="{item["text_x"]}" y="{row_y + 3}" fill="{NEAR_BLACK}" font-size="9" '
            'font-family="\'JetBrains Mono\', monospace">'
            f"{escape(item['label'])}</text>"
        )
    return fragments


def _uml_boxes(spec: UmlClassDiagramSpec) -> dict[str, Box]:
    boxes: dict[str, Box] = {}
    x = 80
    y = 100
    for item in spec.types:
        body_h = 62 + 18 * len(item.attributes) + 18 * len(item.methods)
        if item.x is not None and item.y is not None:
            boxes[item.id] = Box(item.x, item.y, 220, body_h)
            continue
        boxes[item.id] = Box(x, y, 220, body_h)
        x += 280
        if x + 220 > spec.width:
            x = 80
            y += 220
    return boxes


def _uml_sides(source: Box, target: Box) -> tuple[str, str]:
    if source.x + source.w <= target.x:
        return "right", "left"
    if target.x + target.w <= source.x:
        return "left", "right"
    if source.y < target.y:
        return "bottom", "top"
    return "top", "bottom"


def _uml_anchors(
    source: Box,
    target: Box,
    source_side: str,
    target_side: str,
    source_slot: int,
    target_slot: int,
) -> tuple[tuple[int, int], tuple[int, int]]:
    return (
        _box_anchor(source, source_side, source_slot),
        _box_anchor(target, target_side, target_slot),
    )


def _uml_route_points(
    start: tuple[int, int],
    end: tuple[int, int],
    source_box: Box,
    target_box: Box,
    source_side: str,
    target_side: str,
    boxes: dict[str, Box],
    source_id: str,
    target_id: str,
    route_policy: str | None = None,
) -> list[tuple[int, int]]:
    if route_policy == "direct":
        return [start, end]
    if route_policy == "top-lane":
        corridor_y = min(source_box.y, target_box.y) - 22
        return [start, (start[0] + 16, start[1]), (start[0] + 16, corridor_y), (end[0] - 16, corridor_y), (end[0] - 16, end[1]), end]
    if route_policy == "side-lane":
        corridor_x = max(source_box.x + source_box.w, target_box.x + target_box.w) + 26
        return [start, (corridor_x, start[1]), (corridor_x, end[1]), end]

    if source_side in {"right", "left"} and target_side in {"right", "left"}:
        if _uml_has_horizontal_blocker(source_box, target_box, boxes, source_id, target_id):
            corridor_y = min(source_box.y, target_box.y) - 22
            return [start, (start[0] + 16, start[1]), (start[0] + 16, corridor_y), (end[0] - 16, corridor_y), (end[0] - 16, end[1]), end]
        mid_x = (start[0] + end[0]) // 2
        return [start, (mid_x, start[1]), (mid_x, end[1]), end]

    if source_side in {"top", "bottom"} and target_side in {"top", "bottom"}:
        mid_y = (start[1] + end[1]) // 2
        return [start, (start[0], mid_y), (end[0], mid_y), end]

    return [start, (start[0], end[1]), end]


def _uml_label_point(
    points: list[tuple[int, int]],
    label_lane: str | None,
    label_offset: int | None,
) -> tuple[int, int]:
    label_x, label_y = _label_point(points)
    offset = label_offset or 0
    if label_lane == "top":
        top_y = min(point[1] for point in points)
        return (label_x, top_y + offset)
    if label_lane == "bottom":
        bottom_y = max(point[1] for point in points)
        return (label_x, bottom_y + offset)
    if label_lane == "middle":
        return (label_x, label_y + offset)
    return (label_x, label_y + offset)


def _uml_has_horizontal_blocker(
    source_box: Box,
    target_box: Box,
    boxes: dict[str, Box],
    source_id: str,
    target_id: str,
) -> bool:
    left = min(source_box.x + source_box.w, target_box.x + target_box.w)
    right = max(source_box.x, target_box.x)
    row_top = min(source_box.y, target_box.y)
    row_bottom = max(source_box.y + source_box.h, target_box.y + target_box.h)
    for box_id, box in boxes.items():
        if box_id in {source_id, target_id}:
            continue
        overlaps_x = box.x < right and (box.x + box.w) > left
        overlaps_y = box.y < row_bottom and (box.y + box.h) > row_top
        if overlaps_x and overlaps_y:
            return True
    return False


def _box_anchor(box: Box, side: str, slot: int) -> tuple[int, int]:
    slot_positions = [0.34, 0.66, 0.5]
    ratio = slot_positions[slot % len(slot_positions)]
    if side == "right":
        return (box.x + box.w, box.y + int(box.h * ratio))
    if side == "left":
        return (box.x, box.y + int(box.h * ratio))
    if side == "bottom":
        return (box.x + int(box.w * ratio), box.y + box.h)
    return (box.x + int(box.w * ratio), box.y)


def _path_from_points(points: list[tuple[int, int]]) -> str:
    return "M " + " L ".join(f"{x} {y}" for x, y in points)


def _label_point(points: list[tuple[int, int]]) -> tuple[int, int]:
    segments = list(zip(points, points[1:]))
    if not segments:
        return points[0]
    start, end = max(segments, key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]))
    return ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)


def _node_stroke(kind: str) -> str:
    return {
        "external": STONE,
        "service": NEAR_BLACK,
        "store": OLIVE,
        "cloud": BORDER,
    }.get(kind, NEAR_BLACK)


def _edge_style(kind: str, priority: str | None, is_focus: bool) -> tuple[str, float]:
    if is_focus:
        return BRAND, 1.8
    if kind == "primary" or priority == "primary":
        return BRAND, 1.4
    if priority == "background":
        return STONE, 1.0
    return OLIVE, 1.2


def _edge_label_style(kind: str, priority: str | None, is_focus: bool) -> tuple[str, str, int, float]:
    if is_focus or kind == "primary" or priority == "primary":
        return ("primary", BRAND, 8, 1.0)
    if priority == "background":
        return ("background", STONE, 7, 0.72)
    return ("secondary", OLIVE, 8, 0.9)


def _legend_flow_color(flow: str) -> str:
    return {
        "control": BRAND,
        "query": NEAR_BLACK,
        "write": OLIVE,
        "read": STONE,
        "stream": OLIVE,
        "event": STONE,
    }.get(flow, OLIVE)


def _normalize_port(port: str | None, source: Box, target: Box) -> str:
    if port in {"left", "right", "top", "bottom"}:
        return port
    if abs(source.y - target.y) < 8:
        return "right" if source.x <= target.x else "left"
    return "bottom" if source.y < target.y else "top"


def _box_side_anchor(box: Box, side: str) -> tuple[int, int]:
    if side == "left":
        return (box.x, box.y + box.h // 2)
    if side == "right":
        return (box.x + box.w, box.y + box.h // 2)
    if side == "top":
        return (box.x + box.w // 2, box.y)
    return (box.x + box.w // 2, box.y + box.h)


def _chevron_for_segment(
    start: tuple[int, int],
    end: tuple[int, int],
    stroke: str,
    klass: Optional[str] = None,
    stroke_width: float = 1.4,
) -> str:
    x1, y1 = start
    x2, y2 = end
    if x2 > x1:
        d = f"M {x2 - 8} {y2 - 4} L {x2} {y2} L {x2 - 8} {y2 + 4}"
    elif x2 < x1:
        d = f"M {x2 + 8} {y2 - 4} L {x2} {y2} L {x2 + 8} {y2 + 4}"
    elif y2 > y1:
        d = f"M {x2 - 4} {y2 - 8} L {x2} {y2} L {x2 + 4} {y2 - 8}"
    else:
        d = f"M {x2 - 4} {y2 + 8} L {x2} {y2} L {x2 + 4} {y2 + 8}"
    class_attr = f' class="{klass}"' if klass else ""
    return f'<path{class_attr} d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" />'


def _diamond_at_point(start: tuple[int, int], end: tuple[int, int], filled: bool) -> tuple[str, tuple[int, int]]:
    x1, y1 = start
    x2, y2 = end
    fill = OLIVE if filled else PARCHMENT
    if x2 > x1:
        points = [(x1, y1), (x1 + 8, y1 - 5), (x1 + 16, y1), (x1 + 8, y1 + 5)]
        line_start = (x1 + 16, y1)
    elif x2 < x1:
        points = [(x1, y1), (x1 - 8, y1 - 5), (x1 - 16, y1), (x1 - 8, y1 + 5)]
        line_start = (x1 - 16, y1)
    elif y2 > y1:
        points = [(x1, y1), (x1 - 5, y1 + 8), (x1, y1 + 16), (x1 + 5, y1 + 8)]
        line_start = (x1, y1 + 16)
    else:
        points = [(x1, y1), (x1 - 5, y1 - 8), (x1, y1 - 16), (x1 + 5, y1 - 8)]
        line_start = (x1, y1 - 16)
    polygon = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polygon class="uml-diamond" points="{polygon}" fill="{fill}" stroke="{OLIVE}" stroke-width="1.2" />',
        line_start,
    )


def _triangle_at_point(tip: tuple[int, int], toward: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    x1, y1 = toward
    x2, y2 = tip
    if x2 > x1:
        points = [(x2, y2), (x2 - 12, y2 - 6), (x2 - 12, y2 + 6)]
        line_end = (x2 - 12, y2)
    elif x2 < x1:
        points = [(x2, y2), (x2 + 12, y2 - 6), (x2 + 12, y2 + 6)]
        line_end = (x2 + 12, y2)
    elif y2 > y1:
        points = [(x2, y2), (x2 - 6, y2 - 12), (x2 + 6, y2 - 12)]
        line_end = (x2, y2 - 12)
    else:
        points = [(x2, y2), (x2 - 6, y2 + 12), (x2 + 6, y2 + 12)]
        line_end = (x2, y2 + 12)
    polygon = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polygon class="uml-triangle" points="{polygon}" fill="{PARCHMENT}" stroke="{OLIVE}" stroke-width="1.2" />',
        line_end,
    )
