"""Tests for vibe (LLM sentiment analysis)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from polypulse.polymarket import Market
from polypulse.vibe import build_prompt, run_vibe


def _market(**kwargs):
    defaults = dict(
        id="1",
        slug="test-market",
        question="Will it rain tomorrow?",
        description="A market about rain.",
        outcomes=["Yes", "No"],
        outcome_prices=[0.65, 0.35],
        volume=100000,
        volume_24h=5000,
        liquidity=20000,
        active=True,
        end_date="2025-12-31",
        one_day_price_change=-0.02,
    )
    defaults.update(kwargs)
    return Market(**defaults)


class TestBuildPrompt:
    def test_includes_market_data(self):
        m = _market()
        prompt = build_prompt(m)
        assert "Will it rain tomorrow?" in prompt
        assert "5,000" in prompt
        assert "0.65" in prompt

    def test_includes_comments(self):
        m = _market()
        comments = [{"body": "I think yes for sure"}, {"body": "No way"}]
        prompt = build_prompt(m, comments)
        assert "I think yes for sure" in prompt
        assert "No way" in prompt

    def test_no_comments(self):
        m = _market()
        prompt = build_prompt(m, comments=None)
        assert "Recent comments" not in prompt


class TestRunVibe:
    @patch("polypulse.vibe.requests.post")
    @patch("polypulse.vibe._get_api_key", return_value="test-key")
    def test_successful_response(self, mock_key, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"sentiment": "bullish", "summary": "Looking good."}
                        )
                    }
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = run_vibe(_market())
        assert result["sentiment"] == "bullish"
        assert result["summary"] == "Looking good."
        assert result["slug"] == "test-market"

    def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="MOONSHOT_API_KEY"):
                run_vibe(_market())
