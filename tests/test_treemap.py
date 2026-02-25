"""Tests for treemap layout algorithm."""

from polypulse.treemap import Rect, layout_treemap


class TestLayoutTreemap:
    def test_single_value_fills_bounds(self):
        rects = layout_treemap([100.0], Rect(0, 0, 80, 24))
        assert len(rects) == 1
        assert rects[0] == Rect(0, 0, 80, 24)

    def test_two_equal_values(self):
        rects = layout_treemap([50.0, 50.0], Rect(0, 0, 80, 24))
        assert len(rects) == 2
        # Together they should cover the full area (no overlap, no gap)
        total_area = sum(r.w * r.h for r in rects)
        assert total_area == 80 * 24

    def test_preserves_order(self):
        """Output rects match input order, not sorted order."""
        rects = layout_treemap([10.0, 90.0, 50.0], Rect(0, 0, 100, 40))
        assert len(rects) == 3
        # The largest value (90.0, index 1) should have the biggest area
        areas = [r.w * r.h for r in rects]
        assert areas[1] > areas[0]
        assert areas[1] > areas[2]

    def test_proportional_areas(self):
        """Tile areas are roughly proportional to values."""
        rects = layout_treemap([75.0, 25.0], Rect(0, 0, 100, 40))
        areas = [r.w * r.h for r in rects]
        ratio = areas[0] / areas[1]
        # Should be roughly 3:1 (allow rounding tolerance)
        assert 2.0 < ratio < 4.5

    def test_empty_values(self):
        rects = layout_treemap([], Rect(0, 0, 80, 24))
        assert rects == []

    def test_zero_values_equal_split(self):
        rects = layout_treemap([0.0, 0.0, 0.0], Rect(0, 0, 60, 30))
        assert len(rects) == 3
        # All should have some area
        for r in rects:
            assert r.w > 0 and r.h > 0

    def test_all_rects_within_bounds(self):
        rects = layout_treemap([100, 80, 60, 40, 20, 10, 5, 3, 2, 1], Rect(0, 0, 120, 40))
        for r in rects:
            assert r.x >= 0
            assert r.y >= 0
            assert r.x + r.w <= 120
            assert r.y + r.h <= 40

    def test_no_zero_dimension_rects(self):
        rects = layout_treemap([100, 50, 25, 10, 5], Rect(0, 0, 80, 24))
        for r in rects:
            assert r.w >= 1
            assert r.h >= 1
