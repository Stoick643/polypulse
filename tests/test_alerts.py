"""Tests for smart alerts."""

import json
from unittest.mock import patch, MagicMock, call

import pytest

from polypulse.alerts import (
    check_alert,
    clear_snapshots,
    get_snapshot,
    record_snapshot,
    run_alert_loop,
)


@pytest.fixture(autouse=True)
def clean_snapshots():
    """Ensure clean snapshot state for every test."""
    clear_snapshots()
    yield
    clear_snapshots()


class TestSnapshots:
    def test_record_and_get(self):
        record_snapshot("my-market", 0.65, timestamp=1000.0)
        snap = get_snapshot("my-market")
        assert snap == (1000.0, 0.65)

    def test_get_missing_returns_none(self):
        assert get_snapshot("nonexistent") is None


class TestCheckAlert:
    def test_first_check_records_snapshot_no_alert(self):
        triggered = check_alert("m1", 0.65, threshold_pct=5)
        assert triggered is False
        assert get_snapshot("m1") is not None

    def test_small_move_no_alert(self):
        record_snapshot("m1", 0.65)
        triggered = check_alert("m1", 0.66, threshold_pct=5)
        assert triggered is False

    def test_large_move_triggers_alert(self):
        record_snapshot("m1", 0.50)
        callback = MagicMock()
        triggered = check_alert("m1", 0.60, threshold_pct=5, callback=callback)
        assert triggered is True
        callback.assert_called_once()
        # Verify callback args
        args = callback.call_args[0]
        assert args[0] == "m1"       # slug
        assert args[1] == 0.50       # old price
        assert args[2] == 0.60       # new price
        assert args[3] == pytest.approx(20.0)  # change %

    def test_alert_resets_snapshot(self):
        record_snapshot("m1", 0.50)
        check_alert("m1", 0.60, threshold_pct=5, callback=MagicMock())
        # Snapshot should now be at the new price
        snap = get_snapshot("m1")
        assert snap is not None
        assert snap[1] == 0.60


class TestRunAlertLoop:
    @patch("polypulse.alerts.fetch_market")
    def test_loop_checks_all_slugs(self, mock_fetch):
        from polypulse.polymarket import Market

        mock_fetch.side_effect = lambda slug: Market(
            id="1", slug=slug, question="Q", description="",
            outcomes=["Yes", "No"], outcome_prices=[0.5, 0.5],
            volume=1000, volume_24h=100, liquidity=500,
            active=True, end_date="2025-12-31",
        )

        callback = MagicMock()
        run_alert_loop(
            slugs=["a", "b"],
            threshold_pct=5,
            interval_seconds=0,
            callback=callback,
            max_iterations=1,
        )
        # Should have called fetch_market for both slugs
        assert mock_fetch.call_count == 2
