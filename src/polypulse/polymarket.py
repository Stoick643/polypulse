"""Wrapper around the polymarket CLI — parsing, filtering, deduplication."""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Market:
    """Simplified market representation."""

    id: str
    slug: str
    question: str
    description: str
    outcomes: list[str]
    outcome_prices: list[float]
    volume: float
    volume_24h: float
    liquidity: float
    active: bool
    end_date: str
    event_slug: str | None = None
    event_title: str | None = None
    one_day_price_change: float | None = None
    image: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "question": self.question,
            "description": self.description,
            "outcomes": self.outcomes,
            "outcome_prices": self.outcome_prices,
            "volume": self.volume,
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "active": self.active,
            "end_date": self.end_date,
            "event_slug": self.event_slug,
            "event_title": self.event_title,
            "one_day_price_change": self.one_day_price_change,
            "image": self.image,
        }


def parse_market(raw: dict[str, Any]) -> Market:
    """Parse a raw market JSON object into a Market dataclass."""
    # outcomes and outcomePrices are JSON-encoded strings (or None)
    outcomes_raw = raw.get("outcomes")
    outcomes = json.loads(outcomes_raw) if outcomes_raw else []
    prices_raw = raw.get("outcomePrices")
    outcome_prices = [float(p) for p in json.loads(prices_raw)] if prices_raw else []

    # Extract event info if present
    events = raw.get("events") or []
    event_slug = events[0]["slug"] if events else None
    event_title = events[0]["title"] if events else None

    one_day = raw.get("oneDayPriceChange")

    return Market(
        id=str(raw["id"]),
        slug=raw["slug"],
        question=raw["question"],
        description=raw.get("description", ""),
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        volume=float(raw.get("volumeNum", 0) or 0),
        volume_24h=float(raw.get("volume24hr", 0) or 0),
        liquidity=float(raw.get("liquidityNum", 0) or 0),
        active=bool(raw.get("active", False)),
        end_date=raw.get("endDateIso", ""),
        event_slug=event_slug,
        event_title=event_title,
        one_day_price_change=float(one_day) if one_day is not None else None,
        image=raw.get("image"),
    )


def run_polymarket(*args: str) -> str:
    """Run a polymarket CLI command and return stdout.

    Raises subprocess.CalledProcessError on non-zero exit.
    """
    cmd = ["polymarket", *args, "-o", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def fetch_active_markets(limit: int = 50, order: str | None = None) -> list[Market]:
    """Fetch active markets, optionally sorted by a field."""
    args = ["markets", "list", "--active", "true", "--limit", str(limit)]
    if order:
        args.extend(["--order", order])
    stdout = run_polymarket(*args)
    raw_markets = json.loads(stdout)
    return [parse_market(m) for m in raw_markets]


def fetch_market(slug_or_id: str) -> Market:
    """Fetch a single market by slug or ID."""
    stdout = run_polymarket("markets", "get", slug_or_id)
    raw = json.loads(stdout)
    return parse_market(raw)


def search_markets(query: str, limit: int = 10) -> list[Market]:
    """Search markets by keyword."""
    stdout = run_polymarket(
        "markets", "search", query,
        "--limit", str(limit),
    )
    raw_results = json.loads(stdout)
    # Search may return a list directly or nested under a key
    if isinstance(raw_results, dict):
        # Try common keys
        raw_results = raw_results.get("markets", raw_results.get("results", []))
    return [parse_market(m) for m in raw_results]


def fetch_comments(entity_type: str, entity_id: str, limit: int = 25) -> list[dict]:
    """Fetch comments for an entity (event, market, or series)."""
    stdout = run_polymarket(
        "comments", "list",
        "--entity-type", entity_type,
        "--entity-id", entity_id,
        "--limit", str(limit),
    )
    return json.loads(stdout)


def filter_markets(markets: list[Market], patterns: list[str]) -> list[Market]:
    """Remove markets whose slug or question matches any filter pattern (case-insensitive)."""
    filtered = []
    for m in markets:
        slug_lower = m.slug.lower()
        question_lower = m.question.lower()
        if any(p.lower() in slug_lower or p.lower() in question_lower for p in patterns):
            continue
        filtered.append(m)
    return filtered


def dedupe_by_event(markets: list[Market]) -> list[Market]:
    """Keep only the highest-volume market per event.

    Markets without an event are always kept.
    """
    best: dict[str, Market] = {}
    no_event: list[Market] = []

    for m in markets:
        if m.event_slug is None:
            no_event.append(m)
        elif m.event_slug not in best or m.volume_24h > best[m.event_slug].volume_24h:
            best[m.event_slug] = m

    return list(best.values()) + no_event
