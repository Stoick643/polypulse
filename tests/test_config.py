"""Tests for config management."""

import json
from pathlib import Path

from polypulse.config import (
    DEFAULT_CONFIG,
    add_watch,
    load_config,
    remove_watch,
    save_config,
)


def test_load_defaults_when_no_file(tmp_path):
    """Returns default config when file doesn't exist."""
    config = load_config(tmp_path / "missing.json")
    assert config == DEFAULT_CONFIG


def test_load_existing_config(tmp_path):
    """Loads values from an existing config file."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"wallet_address": "0xABC", "top_n_markets": 20}))
    config = load_config(path)
    assert config["wallet_address"] == "0xABC"
    assert config["top_n_markets"] == 20
    # Defaults still present for unset keys
    assert config["alert_threshold_pct"] == 5


def test_load_merges_with_defaults(tmp_path):
    """User config merges with defaults — missing keys get default values."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"watched_markets": ["some-slug"]}))
    config = load_config(path)
    assert config["watched_markets"] == ["some-slug"]
    assert config["refresh_interval_seconds"] == 30


def test_save_and_reload(tmp_path):
    """Config survives a save/load round-trip."""
    path = tmp_path / "config.json"
    config = dict(DEFAULT_CONFIG)
    config["wallet_address"] = "0xDEF"
    save_config(config, path)
    loaded = load_config(path)
    assert loaded["wallet_address"] == "0xDEF"


def test_add_watch(tmp_path):
    """Adding a slug to the watch list persists it."""
    path = tmp_path / "config.json"
    save_config(dict(DEFAULT_CONFIG), path)
    config = add_watch("my-market", path)
    assert "my-market" in config["watched_markets"]
    # Reload to confirm persistence
    assert "my-market" in load_config(path)["watched_markets"]


def test_add_watch_no_duplicates(tmp_path):
    """Adding the same slug twice doesn't create duplicates."""
    path = tmp_path / "config.json"
    save_config(dict(DEFAULT_CONFIG), path)
    add_watch("my-market", path)
    add_watch("my-market", path)
    config = load_config(path)
    assert config["watched_markets"].count("my-market") == 1


def test_remove_watch(tmp_path):
    """Removing a slug from the watch list persists the change."""
    path = tmp_path / "config.json"
    initial = dict(DEFAULT_CONFIG)
    initial["watched_markets"] = ["a", "b", "c"]
    save_config(initial, path)
    config = remove_watch("b", path)
    assert "b" not in config["watched_markets"]
    assert load_config(path)["watched_markets"] == ["a", "c"]
