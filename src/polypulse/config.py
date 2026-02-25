"""Configuration management for PolyPulse."""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "watched_markets": [],
    "wallet_address": "",
    "alert_threshold_pct": 5,
    "alert_interval_seconds": 3600,
    "refresh_interval_seconds": 30,
    "top_n_markets": 10,
    "filter_patterns": [
        "updown",
        "up-or-down",
        "trump",
        "bitcoin",
        "ethereum",
        "btc",
        "eth",
        "sol",
    ],
}


def _config_path() -> Path:
    """Return the path to config.json (next to the project root)."""
    return Path(os.environ.get("POLYPULSE_CONFIG", "config.json"))


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from disk, falling back to defaults for missing keys."""
    path = path or _config_path()
    if path.exists():
        with open(path) as f:
            user_config = json.load(f)
        # Merge: user values override defaults
        merged = {**DEFAULT_CONFIG, **user_config}
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    """Save config to disk."""
    path = path or _config_path()
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def add_watch(slug: str, path: Path | None = None) -> dict[str, Any]:
    """Add a market slug to the watch list. Returns updated config."""
    config = load_config(path)
    if slug not in config["watched_markets"]:
        config["watched_markets"].append(slug)
        save_config(config, path)
    return config


def remove_watch(slug: str, path: Path | None = None) -> dict[str, Any]:
    """Remove a market slug from the watch list. Returns updated config."""
    config = load_config(path)
    if slug in config["watched_markets"]:
        config["watched_markets"].remove(slug)
        save_config(config, path)
    return config
