from __future__ import annotations

import heapq

from ..layout.models import LayoutBox


def _grid(value: float | int, size: int = 4) -> int:
    return int(round(float(value) / size) * size)


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: LayoutBox) -> bool:
    if start[0] == end[0]:
        x = start[0]
        low, high = sorted((start[1], end[1]))
        return box.x < x < box.x + box.w and low < box.y + box.h and high > box.y
    if start[1] == end[1]:
        y = start[1]
        low, high = sorted((start[0], end[0]))
        return box.y < y < box.y + box.h and low < box.x + box.w and high > box.x
    return False


def _simplify(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for point in points:
        if result and result[-1] == point:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if a[0] == b[0] == c[0] or a[1] == b[1] == c[1]:
                result.pop(-2)
            else:
                break
    return result


def route_orthogonal(
    start: tuple[int, int],
    end: tuple[int, int],
    boxes: dict[str, LayoutBox],
    allowed: set[str],
    width: int,
    height: int,
    clearance: int = 20,
) -> list[tuple[int, int]]:
    if start[0] == end[0] or start[1] == end[1]:
        direct = [start, end]
    else:
        direct = [start, (end[0], start[1]), end]
    obstacles = [
        LayoutBox(box.x - 8, box.y - 8, box.w + 16, box.h + 16)
        for node_id, box in boxes.items()
        if node_id not in allowed
    ]
    if not any(_segment_crosses_box(a, b, box) for a, b in zip(direct, direct[1:]) for box in obstacles):
        return _simplify(direct)

    min_x, max_x = 32, width - 32
    min_y, max_y = 64, height - 32
    xs = {start[0], end[0], min_x, max_x}
    ys = {start[1], end[1], min_y, max_y}
    for box in obstacles:
        xs.update({_grid(box.x - clearance), _grid(box.x + box.w + clearance)})
        ys.update({_grid(box.y - clearance), _grid(box.y + box.h + clearance)})
    xs = {value for value in xs if min_x <= value <= max_x}
    ys = {value for value in ys if min_y <= value <= max_y}
    nodes = {(x, y) for x in xs for y in ys} | {start, end}

    def clear(left: tuple[int, int], right: tuple[int, int]) -> bool:
        if left == right or (left[0] != right[0] and left[1] != right[1]):
            return False
        return not any(_segment_crosses_box(left, right, box) for box in obstacles)

    heap: list[tuple[int, int, tuple[int, int], str | None]] = [(0, 0, start, None)]
    best = {(start, None): 0}
    previous: dict[tuple[tuple[int, int], str | None], tuple[tuple[int, int], str | None]] = {}
    counter = 1
    end_state: tuple[tuple[int, int], str | None] | None = None
    while heap:
        cost, _order, point, direction = heapq.heappop(heap)
        state = (point, direction)
        if cost != best.get(state):
            continue
        if point == end:
            end_state = state
            break
        for candidate in nodes:
            if not clear(point, candidate):
                continue
            next_direction = "h" if point[1] == candidate[1] else "v"
            length = abs(point[0] - candidate[0]) + abs(point[1] - candidate[1])
            next_cost = cost + length + (80 if direction and direction != next_direction else 0)
            next_state = (candidate, next_direction)
            if next_cost < best.get(next_state, 10**9):
                best[next_state] = next_cost
                previous[next_state] = state
                heapq.heappush(heap, (next_cost, counter, candidate, next_direction))
                counter += 1
    if end_state is None:
        return _simplify(direct)
    path = []
    state = end_state
    while True:
        path.append(state[0])
        if state[0] == start:
            break
        state = previous[state]
    return _simplify(list(reversed(path)))
