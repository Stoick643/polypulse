"""Tests for all CLI commands."""

import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from polypulse.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# watch / unwatch / list
# ---------------------------------------------------------------------------

class TestWatch:
    def test_watch_adds_slug(self, runner, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"watched_markets": []}))
        with patch("polypulse.cli.add_watch") as mock_add:
            mock_add.return_value = {"watched_markets": ["my-market"]}
            result = runner.invoke(cli, ["watch", "my-market"])
            assert result.exit_code == 0
            mock_add.assert_called_once_with("my-market")

    def test_watch_json_output(self, runner):
        with patch("polypulse.cli.add_watch") as mock_add:
            mock_add.return_value = {"watched_markets": ["slug-a"]}
            result = runner.invoke(cli, ["watch", "slug-a", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "slug-a" in data["watched_markets"]


class TestUnwatch:
    def test_unwatch_removes_slug(self, runner):
        with patch("polypulse.cli.remove_watch") as mock_rm:
            mock_rm.return_value = {"watched_markets": []}
            result = runner.invoke(cli, ["unwatch", "old-slug"])
            assert result.exit_code == 0
            mock_rm.assert_called_once_with("old-slug")


class TestList:
    def test_list_empty(self, runner):
        with patch("polypulse.cli.load_config") as mock_cfg:
            mock_cfg.return_value = {"watched_markets": []}
            result = runner.invoke(cli, ["list"])
            assert result.exit_code == 0

    def test_list_json(self, runner):
        with patch("polypulse.cli.load_config") as mock_cfg:
            mock_cfg.return_value = {"watched_markets": ["a", "b"]}
            result = runner.invoke(cli, ["list", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["watched_markets"] == ["a", "b"]


# ---------------------------------------------------------------------------
# trade
# ---------------------------------------------------------------------------

class TestTrade:
    def test_trade_no_auto(self, runner):
        result = runner.invoke(cli, ["trade"])
        assert result.exit_code == 0
        assert "--auto" in result.output

    @patch("polypulse.cli.fetch_active_markets")
    @patch("polypulse.cli.load_config")
    def test_trade_auto_json(self, mock_cfg, mock_fetch, runner):
        from polypulse.polymarket import Market

        mock_cfg.return_value = {"filter_patterns": []}
        mock_fetch.return_value = [
            Market(
                id="1", slug="hot-market", question="Hot?", description="",
                outcomes=["Yes", "No"], outcome_prices=[0.8, 0.2],
                volume=100000, volume_24h=50000, liquidity=10000,
                active=True, end_date="2025-12-31",
                one_day_price_change=0.05, event_slug="evt-1",
            )
        ]
        result = runner.invoke(cli, ["trade", "--auto", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["signal"] == "BUY"


# ---------------------------------------------------------------------------
# portfolio
# ---------------------------------------------------------------------------

class TestPortfolio:
    def test_portfolio_no_wallet(self, runner):
        with patch("polypulse.cli.load_config") as mock_cfg:
            mock_cfg.return_value = {"wallet_address": ""}
            result = runner.invoke(cli, ["portfolio"])
            assert result.exit_code == 2

    @patch("polypulse.polymarket.run_polymarket")
    @patch("polypulse.cli.load_config")
    def test_portfolio_json(self, mock_cfg, mock_run, runner):
        mock_cfg.return_value = {"wallet_address": "0xABC"}
        mock_run.side_effect = [
            json.dumps({"total_value": "1234.56"}),
            json.dumps([{"market": "m1", "size": "10", "pnl": "5.0"}]),
        ]
        result = runner.invoke(cli, ["portfolio", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["wallet"] == "0xABC"
