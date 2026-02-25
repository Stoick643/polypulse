"""Tests for the web dashboard API."""

import json
from unittest.mock import patch

import pytest

from polypulse.web import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestIndexRoute:
    def test_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"PolyPulse" in resp.data


class TestMarketsApi:
    @patch("polypulse.web.fetch_active_markets")
    @patch("polypulse.web.load_config")
    def test_returns_markets(self, mock_config, mock_fetch, client):
        from polypulse.polymarket import Market
        mock_config.return_value = {"top_n_markets": 10, "filter_patterns": []}
        mock_fetch.return_value = [
            Market(id="1", slug="m1", question="Q?", description="",
                   outcomes=["Yes", "No"], outcome_prices=[0.5, 0.5],
                   volume=1000, volume_24h=500, liquidity=100,
                   active=True, end_date="2025-12-31", one_day_price_change=0.02,
                   event_slug="evt1"),
        ]
        resp = client.get("/api/markets")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["markets"]) >= 1
        assert data["markets"][0]["slug"] == "m1"
        assert "exponent" in data

    @patch("polypulse.web.fetch_active_markets", side_effect=RuntimeError("CLI failed"))
    @patch("polypulse.web.load_config")
    def test_error_returns_500(self, mock_config, mock_fetch, client):
        mock_config.return_value = {"top_n_markets": 10, "filter_patterns": []}
        resp = client.get("/api/markets")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data


class TestSearchApi:
    @patch("polypulse.web._run_polypulse")
    def test_search_returns_results(self, mock_run, client):
        mock_run.return_value = {
            "markets": [{"slug": "found", "question": "Found?", "outcome_prices": [0.5], "volume_24h": 100}]
        }
        resp = client.get("/api/search?q=test")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["markets"]) == 1

    def test_missing_query_returns_400(self, client):
        resp = client.get("/api/search")
        assert resp.status_code == 400


class TestVibeApi:
    @patch("polypulse.web._run_polypulse")
    def test_vibe_returns_sentiment(self, mock_run, client):
        mock_run.return_value = {"slug": "m1", "sentiment": "bullish", "summary": "Looks good."}
        resp = client.get("/api/vibe/m1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sentiment"] == "bullish"

    @patch("polypulse.web._run_polypulse", side_effect=RuntimeError("No API key"))
    def test_vibe_error_returns_500(self, mock_run, client):
        resp = client.get("/api/vibe/m1")
        assert resp.status_code == 500


class TestWatchlistApi:
    @patch("polypulse.web.load_config")
    @patch("polypulse.web.fetch_market")
    def test_watchlist_returns_markets(self, mock_fetch, mock_config, client):
        from polypulse.polymarket import Market
        mock_config.return_value = {"watched_markets": ["m1"]}
        mock_fetch.return_value = Market(
            id="1", slug="m1", question="Q?", description="",
            outcomes=["Yes", "No"], outcome_prices=[0.5, 0.5],
            volume=1000, volume_24h=500, liquidity=100,
            active=True, end_date="2025-12-31", one_day_price_change=0.02)
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["watched_markets"]) == 1

    @patch("polypulse.web.add_watch")
    def test_watch_adds_slug(self, mock_add, client):
        mock_add.return_value = {"watched_markets": ["new-slug"]}
        resp = client.post("/api/watch/new-slug")
        assert resp.status_code == 200
        mock_add.assert_called_once_with("new-slug")

    @patch("polypulse.web.remove_watch")
    def test_unwatch_removes_slug(self, mock_rm, client):
        mock_rm.return_value = {"watched_markets": []}
        resp = client.delete("/api/watch/old-slug")
        assert resp.status_code == 200
        mock_rm.assert_called_once_with("old-slug")


class TestPortfolioApi:
    @patch("polypulse.web.load_config")
    def test_no_wallet_returns_400(self, mock_config, client):
        mock_config.return_value = {"wallet_address": ""}
        resp = client.get("/api/portfolio")
        assert resp.status_code == 400

    @patch("polypulse.web.run_polymarket")
    @patch("polypulse.web.load_config")
    def test_portfolio_returns_data(self, mock_config, mock_run, client):
        mock_config.return_value = {"wallet_address": "0xABC"}
        mock_run.side_effect = [
            json.dumps({"total_value": "1234.56"}),
            json.dumps([{"market": "m1", "pnl": "5.0"}]),
        ]
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["wallet"] == "0xABC"


class TestAlertsApi:
    @patch("polypulse.web.load_alerts_log")
    def test_alerts_returns_log(self, mock_log, client):
        mock_log.return_value = [
            {"timestamp": "2026-02-25T22:00:00Z", "slug": "m1", "old_price": 0.5, "new_price": 0.6, "change_pct": 20.0}
        ]
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["alerts"]) == 1


class TestDetailApi:
    @patch("polypulse.web.run_polymarket")
    def test_detail_returns_price_changes(self, mock_run, client):
        mock_run.return_value = json.dumps({
            "slug": "m1", "question": "Q?", "description": "Desc",
            "outcomePrices": '["0.65","0.35"]',
            "volume24hr": "5000", "liquidityNum": "1000",
            "endDateIso": "2025-12-31", "lastTradePrice": "0.64",
            "oneHourPriceChange": "0.01", "oneDayPriceChange": "-0.02",
            "oneWeekPriceChange": "0.05", "oneMonthPriceChange": "-0.1",
            "oneYearPriceChange": "0.2",
        })
        resp = client.get("/api/detail/m1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["price_changes"]["1h"] == 0.01
        assert data["price_changes"]["1y"] == 0.2


class TestWebCli:
    def test_web_command_exists(self):
        from click.testing import CliRunner
        from polypulse.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--no-open" in result.output
