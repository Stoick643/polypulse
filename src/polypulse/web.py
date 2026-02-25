"""Web dashboard — Flask backend serving polypulse --json data."""

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from polypulse.alerts import load_alerts_log
from polypulse.config import add_watch, load_config, remove_watch
from polypulse.polymarket import fetch_active_markets, fetch_market, filter_markets, dedupe_by_event, run_polymarket
from polypulse.scaling import pick_scale


def _run_polypulse(*args: str) -> dict | list:
    """Run a polypulse CLI command with --json and return parsed output."""
    polypulse_bin = Path(sys.executable).parent / "polypulse"
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + ":" + os.environ.get("PATH", "")}
    cmd = [str(polypulse_bin), *args, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"polypulse {' '.join(args)} failed")
    return json.loads(result.stdout)


def create_app() -> Flask:
    """Create and configure the Flask app."""
    static_dir = Path(__file__).parent / "static"
    app = Flask(__name__, static_folder=str(static_dir))

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/api/markets")
    def api_markets():
        try:
            config = load_config()
            top_n = config.get("top_n_markets", 10)
            patterns = config.get("filter_patterns", [])

            markets = fetch_active_markets(limit=200)
            markets = filter_markets(markets, patterns)
            markets = dedupe_by_event(markets)
            markets.sort(key=lambda m: m.volume_24h, reverse=True)
            top = markets[:top_n]

            volumes = [m.volume_24h for m in top]
            scaled, removed_indices, exponent = pick_scale(volumes)

            kept = [m for i, m in enumerate(top) if i not in removed_indices]
            others_vol = (
                sum(m.volume_24h for m in markets[top_n:])
                + sum(top[i].volume_24h for i in removed_indices)
            )

            result = []
            for i, m in enumerate(kept):
                change = m.one_day_price_change or 0
                result.append({
                    "slug": m.slug,
                    "question": m.question,
                    "price": m.outcome_prices[0] if m.outcome_prices else None,
                    "volume_24h": m.volume_24h,
                    "scaled_volume": scaled[i],
                    "signal": "BUY" if change > 0 else "WATCH",
                    "one_day_change": change,
                })

            if others_vol > 0:
                result.append({
                    "slug": "_others",
                    "question": "Others (combined)",
                    "price": None,
                    "volume_24h": others_vol,
                    "scaled_volume": min(scaled) * 0.5 if scaled else 1.0,
                    "signal": "OTHER",
                    "one_day_change": 0,
                })

            return jsonify({"markets": result, "exponent": exponent})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/search")
    def api_search():
        query = request.args.get("q", "")
        if not query:
            return jsonify({"error": "Missing query parameter ?q="}), 400
        try:
            data = _run_polypulse("search", query)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/market/<slug>")
    def api_market(slug):
        try:
            data = _run_polypulse("search", slug, "--limit", "1")
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/vibe/<slug>")
    def api_vibe(slug):
        try:
            data = _run_polypulse("vibe", slug)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # --- Watch list ---

    @app.route("/api/watchlist")
    def api_watchlist():
        config = load_config()
        slugs = config.get("watched_markets", [])
        markets = []
        for slug in slugs:
            try:
                m = fetch_market(slug)
                markets.append({
                    "slug": m.slug,
                    "question": m.question,
                    "price": m.outcome_prices[0] if m.outcome_prices else None,
                    "volume_24h": m.volume_24h,
                    "one_day_change": m.one_day_price_change or 0,
                })
            except Exception:
                markets.append({"slug": slug, "question": slug, "price": None,
                                "volume_24h": 0, "one_day_change": 0, "error": True})
        return jsonify({"watched_markets": markets})

    @app.route("/api/watch/<slug>", methods=["POST"])
    def api_watch(slug):
        config = add_watch(slug)
        return jsonify({"watched_markets": config["watched_markets"]})

    @app.route("/api/watch/<slug>", methods=["DELETE"])
    def api_unwatch(slug):
        config = remove_watch(slug)
        return jsonify({"watched_markets": config["watched_markets"]})

    # --- Portfolio ---

    @app.route("/api/portfolio")
    def api_portfolio():
        config = load_config()
        wallet = config.get("wallet_address", "")
        if not wallet:
            return jsonify({"error": "No wallet_address in config.json"}), 400
        try:
            value_data = json.loads(run_polymarket("data", "value", wallet))
            positions_data = json.loads(run_polymarket("data", "positions", wallet))
            return jsonify({"wallet": wallet, "value": value_data, "positions": positions_data})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # --- Alerts log ---

    @app.route("/api/alerts")
    def api_alerts():
        log = load_alerts_log()
        return jsonify({"alerts": log})

    # --- Market detail with price changes for charts ---

    @app.route("/api/detail/<slug>")
    def api_detail(slug):
        try:
            raw = json.loads(run_polymarket("markets", "get", slug))
            return jsonify({
                "slug": raw.get("slug"),
                "question": raw.get("question"),
                "description": raw.get("description", ""),
                "price": float(json.loads(raw.get("outcomePrices", "[0]"))[0]) if raw.get("outcomePrices") else None,
                "volume_24h": float(raw.get("volume24hr", 0) or 0),
                "liquidity": float(raw.get("liquidityNum", 0) or 0),
                "end_date": raw.get("endDateIso", ""),
                "last_trade_price": float(raw.get("lastTradePrice", 0) or 0),
                "price_changes": {
                    "1h": float(raw.get("oneHourPriceChange", 0) or 0),
                    "1d": float(raw.get("oneDayPriceChange", 0) or 0),
                    "1w": float(raw.get("oneWeekPriceChange", 0) or 0),
                    "1m": float(raw.get("oneMonthPriceChange", 0) or 0),
                    "1y": float(raw.get("oneYearPriceChange", 0) or 0),
                },
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def run_web(port: int = 8080, open_browser: bool = True) -> None:
    """Start the web dashboard."""
    app = create_app()
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
