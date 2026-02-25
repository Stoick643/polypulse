"""LLM sentiment analysis via Moonshot API — the "Vibe Check"."""

import json
import os
import sys

import requests

from polypulse.polymarket import Market

MOONSHOT_API_URL = "https://api.moonshot.ai/v1/chat/completions"


def _get_api_key() -> str:
    key = os.environ.get("MOONSHOT_API_KEY", "")
    if not key:
        raise RuntimeError(
            "MOONSHOT_API_KEY environment variable is not set. "
            "Export it to use the vibe command."
        )
    return key


def build_prompt(market: Market, comments: list[dict] | None = None) -> str:
    """Build the LLM prompt for sentiment analysis."""
    parts = [
        "You are a prediction market analyst. Given the following market data, "
        "provide a 1-sentence sentiment summary (the 'Vibe Check').",
        "",
        f"Market: {market.question}",
        f"Description: {market.description[:500]}",
        f"Outcomes: {', '.join(market.outcomes)}",
        f"Prices: {', '.join(str(p) for p in market.outcome_prices)}",
        f"24h Volume: ${market.volume_24h:,.0f}",
        f"1-day price change: {market.one_day_price_change}",
    ]

    if comments:
        parts.append("")
        parts.append("Recent comments from traders:")
        for c in comments[:10]:
            body = c.get("body") or c.get("content") or c.get("text", "")
            if body:
                parts.append(f"- {body[:200]}")

    parts.append("")
    parts.append(
        'Respond with JSON: {"sentiment": "bullish|bearish|neutral", "summary": "..."}'
    )
    return "\n".join(parts)


def run_vibe(market: Market, comments: list[dict] | None = None) -> dict:
    """Call the Moonshot LLM and return sentiment analysis.

    Returns: {"slug": str, "sentiment": str, "summary": str}
    """
    api_key = _get_api_key()
    prompt = build_prompt(market, comments)

    response = requests.post(
        MOONSHOT_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "moonshot-v1-8k",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Try to parse JSON from the response
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # LLM didn't return valid JSON — wrap raw text
        parsed = {"sentiment": "unknown", "summary": content.strip()}

    return {
        "slug": market.slug,
        "sentiment": parsed.get("sentiment", "unknown"),
        "summary": parsed.get("summary", content.strip()),
    }
