"""Adaptive power scaling for treemap tile sizing.

The treemap needs tile areas proportional to market volume. But raw 24h
volumes can have extreme ratios (e.g. 8000x between #1 and #10), making
small tiles unreadable. This module computes a power exponent that maps
any volume distribution to a target visual ratio.

Algorithm:
    1. Start with top N markets (sorted descending by volume).
    2. Compute raw ratio = max_volume / min_volume.
    3. If raw ratio ≤ target_ratio → use raw values (p=1, no compression).
    4. Otherwise compute p = ln(target) / ln(raw_ratio), clamped to [0.1, 1.0].
    5. Scale each value as value^p.
    6. If raw ratio is extreme, first try trimming up to 2 smallest markets
       (into "Others" bucket) to reduce the ratio before compressing.

    The result: max_scaled / min_scaled ≈ target_ratio (default 7),
    regardless of the input distribution. One formula replaces discrete
    raw/sqrt/log buckets.
"""

import math


def pick_scale(
    values: list[float],
    max_removals: int = 2,
    target_ratio: float = 7.0,
    min_exponent: float = 0.1,
) -> tuple[list[float], list[int], float]:
    """Compute power-scaled values for treemap sizing.

    Args:
        values: List of volumes, sorted descending.
        max_removals: Max items to trim from the tail before compressing.
        target_ratio: Desired max/min ratio in the output.
        min_exponent: Floor for the power exponent (prevents over-compression).

    Returns:
        (scaled_values, removed_indices, exponent)
        - scaled_values: The transformed values for the kept items.
        - removed_indices: Indices of items moved to "Others" bucket.
        - exponent: The power exponent used (1.0 = raw, 0.5 ≈ sqrt, etc.)
    """
    if not values:
        return [], [], 1.0
    if len(values) == 1:
        return list(values), [], 1.0

    removed: list[int] = []
    current = list(values)
    current_indices = list(range(len(values)))

    # Try trimming smallest items to reduce ratio before compressing
    for _ in range(max_removals + 1):  # +1 for initial check
        ratio = _ratio(current)
        if ratio <= target_ratio:
            # No compression needed
            return current, removed, 1.0

        # If we haven't exhausted removals, try trimming
        if len(removed) < max_removals and len(current) > 2:
            removed.append(current_indices.pop())
            current.pop()
        else:
            break

    # Compute the exponent: ratio^p = target → p = ln(target) / ln(ratio)
    ratio = _ratio(current)
    if ratio <= target_ratio:
        return current, removed, 1.0

    p = math.log(target_ratio) / math.log(ratio)
    p = max(p, min_exponent)

    scaled = [v ** p for v in current]
    return scaled, removed, round(p, 3)


def _ratio(values: list[float]) -> float:
    """Compute max/min ratio, handling zeros."""
    if not values:
        return 1.0
    lo = min(values)
    hi = max(values)
    if lo <= 0:
        return float("inf")
    return hi / lo
