"""Tests for the polymarket CLI wrapper, filtering, and deduplication."""

import json
from unittest.mock import patch

import pytest

from polypulse.polymarket import (
    Market,
    dedupe_by_event,
    fetch_active_markets,
    fetch_market,
    filter_markets,
    parse_market,
    search_markets,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _raw_market(
    id="1",
    slug="test-market",
    question="Will it rain?",
    description="A test market.",
    outcomes='["Yes","No"]',
    outcomePrices='["0.65","0.35"]',
    volumeNum="100000",
    volume24hr="5000",
    liquidityNum="20000",
    active=True,
    endDateIso="2025-12-31",
    oneDayPriceChange="-0.02",
    image=None,
    event_slug=None,
    event_title=None,
):
    raw = {
        "id": id,
        "slug": slug,
        "question": question,
        "description": description,
        "outcomes": outcomes,
        "outcomePrices": outcomePrices,
        "volumeNum": volumeNum,
        "volume24hr": volume24hr,
        "liquidityNum": liquidityNum,
        "active": active,
        "endDateIso": endDateIso,
        "oneDayPriceChange": oneDayPriceChange,
        "image": image,
    }
    if event_slug:
        raw["events"] = [{"slug": event_slug, "title": event_title or event_slug}]
    else:
        raw["events"] = []
    return raw


# ---------------------------------------------------------------------------
# parse_market
# ---------------------------------------------------------------------------

class TestParseMarket:
    def test_basic_fields(self):
        raw = _raw_market()
        m = parse_market(raw)
        assert m.id == "1"
        assert m.slug == "test-market"
        assert m.question == "Will it rain?"
        assert m.outcomes == ["Yes", "No"]
        assert m.outcome_prices == [0.65, 0.35]
        assert m.volume == 100000.0
        assert m.volume_24h == 5000.0

    def test_event_extraction(self):
        raw = _raw_market(event_slug="my-event", event_title="My Event")
        m = parse_market(raw)
        assert m.event_slug == "my-event"
        assert m.event_title == "My Event"

    def test_no_events(self):
        raw = _raw_market()
        m = parse_market(raw)
        assert m.event_slug is None
        assert m.event_title is None

    def test_missing_optional_fields(self):
        raw = _raw_market(oneDayPriceChange=None, volumeNum=None, volume24hr=None)
        m = parse_market(raw)
        assert m.one_day_price_change is None
        assert m.volume == 0.0
        assert m.volume_24h == 0.0

    def test_to_dict_roundtrip(self):
        raw = _raw_market(event_slug="evt")
        m = parse_market(raw)
        d = m.to_dict()
        assert d["slug"] == "test-market"
        assert d["event_slug"] == "evt"
        assert isinstance(d["outcome_prices"], list)


# ---------------------------------------------------------------------------
# filter_markets
# ---------------------------------------------------------------------------

class TestFilterMarkets:
    def _make_market(self, slug, question="Some question"):
        raw = _raw_market(slug=slug, question=question)
        return parse_market(raw)

    def test_filters_by_slug(self):
        markets = [self._make_market("btc-up-or-down"), self._make_market("election-winner")]
        result = filter_markets(markets, ["btc"])
        assert len(result) == 1
        assert result[0].slug == "election-winner"

    def test_filters_by_question(self):
        markets = [
            self._make_market("some-slug", question="Will Bitcoin go up?"),
            self._make_market("other-slug", question="Who wins the election?"),
        ]
        result = filter_markets(markets, ["bitcoin"])
        assert len(result) == 1
        assert result[0].slug == "other-slug"

    def test_case_insensitive(self):
        markets = [self._make_market("ETHEREUM-price")]
        result = filter_markets(markets, ["ethereum"])
        assert len(result) == 0

    def test_no_patterns_keeps_all(self):
        markets = [self._make_market("a"), self._make_market("b")]
        result = filter_markets(markets, [])
        assert len(result) == 2

    def test_multiple_patterns(self):
        markets = [
            self._make_market("btc-thing"),
            self._make_market("eth-thing"),
            self._make_market("politics"),
        ]
        result = filter_markets(markets, ["btc", "eth"])
        assert len(result) == 1
        assert result[0].slug == "politics"


# ---------------------------------------------------------------------------
# dedupe_by_event
# ---------------------------------------------------------------------------

class TestDedupeByEvent:
    def _make_market(self, slug, event_slug=None, volume_24h=1000):
        raw = _raw_market(slug=slug, volume24hr=str(volume_24h), event_slug=event_slug)
        return parse_market(raw)

    def test_keeps_highest_volume_per_event(self):
        markets = [
            self._make_market("low", event_slug="evt-a", volume_24h=100),
            self._make_market("high", event_slug="evt-a", volume_24h=9000),
            self._make_market("mid", event_slug="evt-a", volume_24h=500),
        ]
        result = dedupe_by_event(markets)
        assert len(result) == 1
        assert result[0].slug == "high"

    def test_different_events_kept(self):
        markets = [
            self._make_market("a", event_slug="evt-1", volume_24h=100),
            self._make_market("b", event_slug="evt-2", volume_24h=200),
        ]
        result = dedupe_by_event(markets)
        assert len(result) == 2

    def test_no_event_always_kept(self):
        markets = [
            self._make_market("a", event_slug=None),
            self._make_market("b", event_slug=None),
            self._make_market("c", event_slug="evt-1"),
        ]
        result = dedupe_by_event(markets)
        # 2 no-event + 1 event
        assert len(result) == 3

    def test_empty_list(self):
        assert dedupe_by_event([]) == []


# ---------------------------------------------------------------------------
# CLI wrapper (mocked subprocess)
# ---------------------------------------------------------------------------

class TestFetchActiveMarkets:
    @patch("polypulse.polymarket.run_polymarket")
    def test_returns_parsed_markets(self, mock_run):
        raw = [_raw_market(id="1", slug="m1"), _raw_market(id="2", slug="m2")]
        mock_run.return_value = json.dumps(raw)
        markets = fetch_active_markets(limit=2)
        assert len(markets) == 2
        assert markets[0].slug == "m1"
        mock_run.assert_called_once()

    @patch("polypulse.polymarket.run_polymarket")
    def test_passes_correct_args(self, mock_run):
        mock_run.return_value = "[]"
        fetch_active_markets(limit=10, order="liquidity_num")
        args = mock_run.call_args[0]
        assert "markets" in args
        assert "--limit" in args
        assert "10" in args
        assert "liquidity_num" in args


class TestFetchMarket:
    @patch("polypulse.polymarket.run_polymarket")
    def test_returns_single_market(self, mock_run):
        mock_run.return_value = json.dumps(_raw_market(slug="my-slug"))
        m = fetch_market("my-slug")
        assert m.slug == "my-slug"


class TestSearchMarkets:
    @patch("polypulse.polymarket.run_polymarket")
    def test_search_list_response(self, mock_run):
        raw = [_raw_market(slug="found-it")]
        mock_run.return_value = json.dumps(raw)
        results = search_markets("found")
        assert len(results) == 1
        assert results[0].slug == "found-it"

    @patch("polypulse.polymarket.run_polymarket")
    def test_search_dict_response(self, mock_run):
        """Some versions may return {markets: [...]}."""
        raw = {"markets": [_raw_market(slug="nested")]}
        mock_run.return_value = json.dumps(raw)
        results = search_markets("nested")
        assert len(results) == 1
        assert results[0].slug == "nested"

    @patch("polypulse.polymarket.run_polymarket")
    def test_search_empty(self, mock_run):
        mock_run.return_value = "[]"
        results = search_markets("nothing")
        assert results == []
