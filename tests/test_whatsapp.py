"""Tests for WhatsApp bot — intent parsing, formatting, webhook."""

import json
from unittest.mock import patch, MagicMock

import pytest

from polypulse.whatsapp import (
    create_bot_app,
    format_response,
    handle_message,
    parse_intent,
)


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

class TestParseIntent:
    def test_movers(self):
        assert parse_intent("movers")[0] == "movers"
        assert parse_intent("what's moving")[0] == "movers"
        assert parse_intent("What's moving?")[0] == "movers"
        assert parse_intent("top")[0] == "movers"
        assert parse_intent("hot")[0] == "movers"

    def test_vibe_with_arg(self):
        cmd, arg = parse_intent("vibe will-gta-6-cost-100")
        assert cmd == "vibe"
        assert arg == "will-gta-6-cost-100"

    def test_vibe_no_arg(self):
        cmd, arg = parse_intent("vibe")
        assert cmd == "vibe"
        assert arg == ""

    def test_search(self):
        cmd, arg = parse_intent("search election")
        assert cmd == "search"
        assert arg == "election"

    def test_watch(self):
        cmd, arg = parse_intent("watch some-market")
        assert cmd == "watch"
        assert arg == "some-market"

    def test_unwatch(self):
        cmd, arg = parse_intent("unwatch some-market")
        assert cmd == "unwatch"
        assert arg == "some-market"

    def test_list(self):
        assert parse_intent("list")[0] == "list"
        assert parse_intent("watchlist")[0] == "list"

    def test_portfolio(self):
        assert parse_intent("portfolio")[0] == "portfolio"
        assert parse_intent("pnl")[0] == "portfolio"

    def test_help(self):
        assert parse_intent("help")[0] == "help"
        assert parse_intent("?")[0] == "help"
        assert parse_intent("hi")[0] == "help"

    def test_unknown_returns_help(self):
        assert parse_intent("asdfghjkl")[0] == "help"

    def test_preserves_argument_case(self):
        _, arg = parse_intent("search OpenAI Launch")
        assert arg == "OpenAI Launch"


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------

class TestFormatResponse:
    def test_help(self):
        text = format_response("help", {})
        assert "PolyPulse Bot" in text
        assert "movers" in text

    def test_movers(self):
        data = {"suggestions": [
            {"slug": "m1", "question": "Will X?", "price": 0.65, "volume_24h": 500000, "signal": "BUY"},
            {"slug": "m2", "question": "Will Y?", "price": 0.30, "volume_24h": 1000, "signal": "WATCH"},
        ]}
        text = format_response("movers", data)
        assert "Top Movers" in text
        assert "Will X?" in text
        assert "📈" in text
        assert "$500K" in text

    def test_movers_empty(self):
        text = format_response("movers", {"suggestions": []})
        assert "No movers" in text

    def test_vibe(self):
        data = {"slug": "m1", "sentiment": "bullish", "summary": "Looking good."}
        text = format_response("vibe", data)
        assert "🟢" in text
        assert "BULLISH" in text
        assert "Looking good." in text

    def test_search(self):
        data = {"markets": [
            {"slug": "m1", "question": "Q?", "outcome_prices": [0.5], "volume_24h": 100},
        ]}
        text = format_response("search", data)
        assert "Search Results" in text
        assert "Q?" in text

    def test_search_empty(self):
        text = format_response("search", {"markets": []})
        assert "No results" in text

    def test_watch(self):
        text = format_response("watch", {"watched_markets": ["a", "b"]})
        assert "Watching" in text
        assert "2 total" in text

    def test_unwatch(self):
        text = format_response("unwatch", {"watched_markets": ["a"]})
        assert "Unwatched" in text

    def test_list(self):
        text = format_response("list", {"watched_markets": ["slug-a", "slug-b"]})
        assert "slug-a" in text
        assert "slug-b" in text

    def test_list_empty(self):
        text = format_response("list", {"watched_markets": []})
        assert "No watched" in text

    def test_portfolio(self):
        data = {"wallet": "0xABCDEF1234567890", "value": {"total": "100"}, "positions": []}
        text = format_response("portfolio", data)
        assert "Portfolio" in text

    def test_truncation(self):
        data = {"markets": [{"slug": f"m{i}", "question": "Q?" * 200, "outcome_prices": [0.5], "volume_24h": 0} for i in range(100)]}
        text = format_response("search", data)
        assert len(text) <= 4096


# ---------------------------------------------------------------------------
# handle_message (mocked polypulse)
# ---------------------------------------------------------------------------

class TestHandleMessage:
    @patch("polypulse.whatsapp._run_polypulse")
    def test_movers(self, mock_run):
        mock_run.return_value = {"suggestions": [{"slug": "m1", "question": "Q?", "price": 0.5, "volume_24h": 1000, "signal": "BUY"}]}
        reply = handle_message("movers")
        assert "Top Movers" in reply
        mock_run.assert_called_once_with("trade", "--auto")

    @patch("polypulse.whatsapp._run_polypulse")
    def test_vibe(self, mock_run):
        mock_run.return_value = {"slug": "m1", "sentiment": "bullish", "summary": "Good."}
        reply = handle_message("vibe m1")
        assert "BULLISH" in reply

    def test_vibe_no_arg(self):
        reply = handle_message("vibe")
        assert "Usage" in reply

    @patch("polypulse.whatsapp._run_polypulse")
    def test_error_handling(self, mock_run):
        mock_run.side_effect = RuntimeError("CLI crashed")
        reply = handle_message("movers")
        assert "Error" in reply

    def test_help(self):
        reply = handle_message("hello")
        assert "PolyPulse Bot" in reply


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

class TestWebhook:
    @pytest.fixture
    def client(self):
        app = create_bot_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @patch("polypulse.whatsapp.handle_message")
    def test_webhook_returns_twiml(self, mock_handle, client):
        mock_handle.return_value = "Hello back!"
        resp = client.post("/webhook", data={"Body": "hello", "From": "whatsapp:+1234"})
        assert resp.status_code == 200
        assert b"Hello back!" in resp.data
        assert b"Response" in resp.data  # TwiML

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_bot_command_exists(self):
        from click.testing import CliRunner
        from polypulse.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["bot", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
