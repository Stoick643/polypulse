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
    @patch("polypulse.web._run_polypulse")
    def test_returns_suggestions(self, mock_run, client):
        mock_run.return_value = {
            "suggestions": [
                {"slug": "m1", "question": "Q?", "price": 0.5, "volume_24h": 1000, "signal": "BUY"}
            ]
        }
        resp = client.get("/api/markets")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["slug"] == "m1"

    @patch("polypulse.web._run_polypulse", side_effect=RuntimeError("CLI failed"))
    def test_error_returns_500(self, mock_run, client):
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


class TestWebCli:
    def test_web_command_exists(self):
        from click.testing import CliRunner
        from polypulse.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--no-open" in result.output
