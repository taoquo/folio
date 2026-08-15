from __future__ import annotations


def clean_polyline(points: list[tuple[int, int]], grid: int = 4) -> tuple[tuple[int, int], ...]:
    snapped: list[tuple[int, int]] = []
    for index, point in enumerate(points):
        resolved = point if index in {0, len(points) - 1} else tuple(int(round(value / grid) * grid) for value in point)
        if not snapped or snapped[-1] != resolved:
            snapped.append(resolved)
        while len(snapped) >= 3:
            a, b, c = snapped[-3:]
            if a[0] == b[0] == c[0] or a[1] == b[1] == c[1]:
                snapped.pop(-2)
            else:
                break
    return tuple(snapped)
