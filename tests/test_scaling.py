"""Tests for adaptive power scaling."""

import math

import pytest

from polypulse.scaling import pick_scale


class TestPickScale:
    def test_small_ratio_no_compression(self):
        """Ratio < target → raw values, p=1."""
        values = [100, 80, 60, 50, 30, 20]  # ratio 5x
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        assert p == 1.0
        assert removed == []
        assert scaled == values

    def test_exact_target_no_compression(self):
        """Ratio == target → raw values, p=1."""
        values = [70, 10]  # ratio 7x
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        assert p == 1.0
        assert scaled == values

    def test_output_ratio_matches_target(self):
        """For any large ratio, output ratio should ≈ target."""
        values = [10000, 5000, 1000, 500, 100, 50, 10]
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        kept_values = scaled
        output_ratio = max(kept_values) / min(kept_values)
        assert output_ratio == pytest.approx(7.0, rel=0.15)

    def test_extreme_ratio_still_hits_target(self):
        """Even with 10000x ratio, output should ≈ target."""
        values = [10_000_000, 1_000_000, 100_000, 10_000, 1_000]
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        # After removing up to 2, compute output ratio of kept
        output_ratio = max(scaled) / min(scaled)
        assert output_ratio == pytest.approx(7.0, rel=0.2)

    def test_trims_before_compressing(self):
        """If trimming 1-2 items gets ratio below target, no compression."""
        # 100, 90, 80, 70, 1 → ratio 100x
        # Remove 1 → 100/70 = 1.4x → p=1
        values = [100, 90, 80, 70, 1]
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        assert len(removed) >= 1
        assert p == 1.0

    def test_trim_plus_compress(self):
        """Sometimes trim reduces ratio but not enough → still compresses."""
        # 10000, 500, 200, 100, 3, 1 → ratio 10000x
        # Remove 1 → 10000/3=3333x, remove 3 → 10000/100=100x → needs compression
        values = [10000, 500, 200, 100, 3, 1]
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        assert len(removed) == 2
        assert p < 1.0
        output_ratio = max(scaled) / min(scaled)
        assert output_ratio == pytest.approx(7.0, rel=0.15)

    def test_exponent_decreases_with_larger_ratio(self):
        """Higher input ratio → smaller exponent for same target."""
        _, _, p1 = pick_scale([100, 10], target_ratio=7.0, max_removals=0)
        _, _, p2 = pick_scale([10000, 10], target_ratio=7.0, max_removals=0)
        assert p1 > p2

    def test_exponent_clamped_to_min(self):
        """Exponent doesn't go below min_exponent."""
        values = [10**20, 1]
        _, _, p = pick_scale(values, target_ratio=7.0, min_exponent=0.1, max_removals=0)
        assert p >= 0.1

    def test_empty_list(self):
        scaled, removed, p = pick_scale([])
        assert scaled == []
        assert removed == []
        assert p == 1.0

    def test_single_value(self):
        scaled, removed, p = pick_scale([42])
        assert p == 1.0
        assert scaled == [42]

    def test_all_equal(self):
        values = [100, 100, 100]
        scaled, removed, p = pick_scale(values)
        assert p == 1.0
        assert removed == []

    def test_removed_indices_are_from_tail(self):
        """Removed indices are the last items (smallest volumes)."""
        values = [1000, 500, 200, 100, 1]
        _, removed, _ = pick_scale(values)
        for idx in removed:
            assert idx >= len(values) - 2

    def test_preserves_order(self):
        """Scaled values maintain the same relative order as input."""
        values = [5000, 3000, 1000, 500, 100]
        scaled, _, _ = pick_scale(values, max_removals=0)
        for i in range(len(scaled) - 1):
            assert scaled[i] >= scaled[i + 1]

    def test_real_world_data(self):
        """Test with the actual volume distribution we observed."""
        values = [7_589_291, 1_238_499, 779_964, 688_426, 465_289,
                  267_835, 82_536, 46_515, 34_829, 14_039]
        scaled, removed, p = pick_scale(values, target_ratio=7.0)
        output_ratio = max(scaled) / min(scaled)
        assert 5.0 <= output_ratio <= 9.0
        assert p < 1.0
        assert len(removed) <= 2
