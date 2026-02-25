"""Squarified treemap layout algorithm."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int


def layout_treemap(values: list[float], bounds: Rect) -> list[Rect]:
    """Compute a squarified treemap layout.

    Args:
        values: List of positive values (e.g. volume_24h). Order is preserved.
        bounds: The bounding rectangle to fill.

    Returns:
        List of Rects, one per value, in the same order as input.
    """
    if not values or bounds.w <= 0 or bounds.h <= 0:
        return [Rect(bounds.x, bounds.y, 0, 0) for _ in values]

    total = sum(values)
    if total == 0:
        # Equal split
        n = len(values)
        values = [1.0] * n
        total = float(n)

    # Build index-value pairs sorted by value descending for better layout
    indexed = sorted(enumerate(values), key=lambda iv: -iv[1])
    sorted_values = [v for _, v in indexed]
    original_indices = [i for i, _ in indexed]

    rects_sorted = _squarify(sorted_values, total, bounds)

    # Restore original order
    result = [Rect(0, 0, 0, 0)] * len(values)
    for i, orig_idx in enumerate(original_indices):
        result[orig_idx] = rects_sorted[i]
    return result


def _squarify(values: list[float], total: float, bounds: Rect) -> list[Rect]:
    """Recursive squarified layout on sorted (descending) values."""
    if not values:
        return []
    if len(values) == 1:
        return [Rect(bounds.x, bounds.y, max(bounds.w, 1), max(bounds.h, 1))]
    if bounds.w <= 0 or bounds.h <= 0:
        return [Rect(bounds.x, bounds.y, 0, 0) for _ in values]

    area = bounds.w * bounds.h

    # Try adding items to a row/column and pick the split that gives best aspect ratios
    best_split = 1
    best_worst = float("inf")

    for split in range(1, len(values) + 1):
        row = values[:split]
        row_sum = sum(row)
        row_frac = row_sum / total if total else 1.0

        if bounds.w >= bounds.h:
            # Lay out row as a vertical strip on the left
            strip_w = max(1, round(bounds.w * row_frac))
            strip_h = bounds.h
        else:
            # Lay out row as a horizontal strip on top
            strip_w = bounds.w
            strip_h = max(1, round(bounds.h * row_frac))

        # Compute worst aspect ratio in this strip
        worst = 0.0
        for v in row:
            item_frac = v / row_sum if row_sum else 1.0 / len(row)
            if bounds.w >= bounds.h:
                iw = strip_w
                ih = max(1, round(strip_h * item_frac))
            else:
                iw = max(1, round(strip_w * item_frac))
                ih = strip_h
            aspect = max(iw / ih, ih / iw) if iw and ih else float("inf")
            worst = max(worst, aspect)

        if worst <= best_worst:
            best_worst = worst
            best_split = split
        else:
            break  # Aspect ratios getting worse, stop

    # Lay out the chosen row
    row = values[:best_split]
    rest = values[best_split:]
    row_sum = sum(row)
    row_frac = row_sum / total if total else 1.0

    rects = []
    if bounds.w >= bounds.h:
        strip_w = max(1, round(bounds.w * row_frac))
        cy = bounds.y
        for i, v in enumerate(row):
            item_frac = v / row_sum if row_sum else 1.0 / len(row)
            if i == len(row) - 1:
                ih = bounds.y + bounds.h - cy
            else:
                ih = max(1, round(bounds.h * item_frac))
            rects.append(Rect(bounds.x, cy, strip_w, max(ih, 1)))
            cy += ih
        remaining = Rect(bounds.x + strip_w, bounds.y, bounds.w - strip_w, bounds.h)
    else:
        strip_h = max(1, round(bounds.h * row_frac))
        cx = bounds.x
        for i, v in enumerate(row):
            item_frac = v / row_sum if row_sum else 1.0 / len(row)
            if i == len(row) - 1:
                iw = bounds.x + bounds.w - cx
            else:
                iw = max(1, round(bounds.w * item_frac))
            rects.append(Rect(cx, bounds.y, max(iw, 1), strip_h))
            cx += iw
        remaining = Rect(bounds.x, bounds.y + strip_h, bounds.w, bounds.h - strip_h)

    rest_total = total - row_sum
    if rest:
        rects.extend(_squarify(rest, rest_total, remaining))

    return rects
