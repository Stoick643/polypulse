"""Web dashboard — Flask backend serving polypulse --json data."""

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from polypulse.config import load_config
from polypulse.polymarket import fetch_active_markets, filter_markets, dedupe_by_event
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

    return app


def run_web(port: int = 8080, open_browser: bool = True) -> None:
    """Start the web dashboard."""
    app = create_app()
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
