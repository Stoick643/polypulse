"""Web dashboard — Flask backend serving polypulse --json data."""

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory


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
            data = _run_polypulse("trade", "--auto")
            return jsonify(data)
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
