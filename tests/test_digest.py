"""Tests for the daily digest emailer."""

import json
from unittest.mock import patch, MagicMock, call

import pytest
from click.testing import CliRunner

from polypulse.digest import fetch_digest_data, render_html, send_email


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

MOCK_MOVERS = {
    "suggestions": [
        {"slug": "market-a", "question": "Will A happen?", "price": 0.65, "volume_24h": 500000, "signal": "BUY"},
        {"slug": "market-b", "question": "Will B happen?", "price": 0.30, "volume_24h": 100000, "signal": "WATCH"},
        {"slug": "market-c", "question": "Will C happen?", "price": 0.80, "volume_24h": 50000, "signal": "BUY"},
    ]
}

MOCK_VIBE = {"slug": "market-a", "sentiment": "bullish", "summary": "Looking good."}


# ---------------------------------------------------------------------------
# fetch_digest_data
# ---------------------------------------------------------------------------

class TestFetchDigestData:
    def test_gathers_movers_and_vibes(self):
        vibe_calls = []
        def mock_vibe(slug):
            vibe_calls.append(slug)
            return {"slug": slug, "sentiment": "bullish", "summary": f"Vibe for {slug}"}

        data = fetch_digest_data(
            top_movers_fn=lambda: MOCK_MOVERS,
            vibe_fn=mock_vibe,
            num_vibes=2,
        )
        assert "date" in data
        assert len(data["movers"]) == 3
        assert len(data["vibes"]) == 2
        assert vibe_calls == ["market-a", "market-b"]

    def test_vibe_error_handled(self):
        def failing_vibe(slug):
            raise RuntimeError("LLM down")

        data = fetch_digest_data(
            top_movers_fn=lambda: MOCK_MOVERS,
            vibe_fn=failing_vibe,
            num_vibes=1,
        )
        assert len(data["vibes"]) == 1
        assert data["vibes"][0]["sentiment"] == "error"

    def test_no_vibes_requested(self):
        data = fetch_digest_data(
            top_movers_fn=lambda: MOCK_MOVERS,
            vibe_fn=lambda s: MOCK_VIBE,
            num_vibes=0,
        )
        assert data["vibes"] == []


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------

class TestRenderHtml:
    def test_contains_movers(self):
        data = {
            "date": "2026-02-25",
            "movers": MOCK_MOVERS["suggestions"],
            "vibes": [],
        }
        html = render_html(data)
        assert "Will A happen?" in html
        assert "Will B happen?" in html
        assert "BUY" in html
        assert "WATCH" in html
        assert "$500K" in html

    def test_contains_vibes(self):
        data = {
            "date": "2026-02-25",
            "movers": [],
            "vibes": [MOCK_VIBE],
        }
        html = render_html(data)
        assert "market-a" in html
        assert "Looking good." in html
        assert "🟢" in html

    def test_contains_date(self):
        data = {"date": "2026-02-25", "movers": [], "vibes": []}
        html = render_html(data)
        assert "2026-02-25" in html

    def test_is_valid_html(self):
        data = {"date": "2026-02-25", "movers": MOCK_MOVERS["suggestions"], "vibes": [MOCK_VIBE]}
        html = render_html(data)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_empty_movers_and_vibes(self):
        data = {"date": "2026-02-25", "movers": [], "vibes": []}
        html = render_html(data)
        assert "PolyPulse Daily Digest" in html


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------

class TestSendEmail:
    @patch("polypulse.digest.smtplib.SMTP")
    def test_sends_via_smtp(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(
            "<html>test</html>",
            "user@example.com",
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_user="me@test.com",
            smtp_password="secret",
        )

        mock_smtp_cls.assert_called_once_with("smtp.test.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("me@test.com", "secret")
        mock_server.sendmail.assert_called_once()

    def test_missing_credentials_raises(self):
        with pytest.raises(RuntimeError, match="SMTP credentials"):
            send_email("<html>test</html>", "user@example.com",
                       smtp_user="", smtp_password="")


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

class TestDigestCli:
    @patch("polypulse.digest.fetch_digest_data")
    def test_preview_prints_html(self, mock_fetch):
        mock_fetch.return_value = {
            "date": "2026-02-25",
            "movers": MOCK_MOVERS["suggestions"],
            "vibes": [MOCK_VIBE],
        }
        runner = CliRunner()
        from polypulse.cli import cli
        result = runner.invoke(cli, ["digest", "--preview"])
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output
        assert "PolyPulse Daily Digest" in result.output

    @patch("polypulse.digest.fetch_digest_data")
    def test_json_output(self, mock_fetch):
        mock_fetch.return_value = {
            "date": "2026-02-25",
            "movers": MOCK_MOVERS["suggestions"],
            "vibes": [MOCK_VIBE],
        }
        runner = CliRunner()
        from polypulse.cli import cli
        result = runner.invoke(cli, ["digest", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["date"] == "2026-02-25"
        assert len(data["movers"]) == 3

    @patch("polypulse.cli.load_config")
    @patch("polypulse.digest.fetch_digest_data")
    def test_no_recipient_exits_2(self, mock_fetch, mock_cfg):
        mock_fetch.return_value = {"date": "2026-02-25", "movers": [], "vibes": []}
        mock_cfg.return_value = {"digest_recipient": ""}
        runner = CliRunner()
        from polypulse.cli import cli
        result = runner.invoke(cli, ["digest"], env={"POLYPULSE_DIGEST_RECIPIENT": ""})
        assert result.exit_code == 2
