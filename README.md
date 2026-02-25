# PolyPulse CLI

> **The smart terminal layer for Polymarket — filtered markets, live heatmaps, AI sentiment, and machine-readable output.**

A terminal-based intelligence dashboard that aggregates high-volume opportunities and monitors personal positions using the `polymarket-cli`.

## Why PolyPulse?

The raw `polymarket-cli` dumps everything. PolyPulse adds a **smart layer** on top:

- **Curation** — Filters noise (crypto spam, duplicate sub-markets), surfaces the top movers by volume. You see what matters, not 500 markets.
- **Visual Intelligence** — A treemap heatmap tells you in 1 second what's hot. Raw CLI output doesn't.
- **Sentiment in One Line** — "Vibe Check" turns market data + comments into a human sentence via LLM. No one else in the chain does this.
- **Alerts Without Babysitting** — Set it and forget it. Get notified when something moves.
- **Composability** — The `--json` flag means any developer can build on top without learning the Polymarket API. PolyPulse becomes the smart middle layer.

### Who Is This For?

| Audience | Why |
|----------|-----|
| **Traders** | Quick dashboard, alerts, portfolio view — no browser needed |
| **Bot builders** | Wrap `polypulse` for Telegram/Discord bots, get filtered + sentiment-enriched data for free |
| **Researchers / Journalists** | Track prediction markets from terminal, get AI-summarized sentiment |
| **Agent developers** | Use as a skill — "what does the market think about X?" in any agent |
| **Tinkerers** | It's a cool CLI tool, open source, hackable |

## Installation

### Requirements
- Python 3.11+
- [`polymarket-cli`](https://github.com/polymarket/polymarket-cli) installed and configured
- (Optional) Moonshot API key for LLM sentiment analysis

### Install from source

```bash
git clone https://github.com/youruser/poly-pulse.git
cd poly-pulse
pip install .
```

### Setup

```bash
cp config.example.json config.json   # Edit with your settings
export MOONSHOT_API_KEY=your_key     # For vibe check feature
```

## Core Functionality

### The "Heatmap" View
Poll `polymarket markets list --active true` to display a live-updating TUI (Terminal User Interface) of the top 10 markets by 24h volume. Treemap-style layout where tile size represents volume and color represents price sentiment. Treemap uses adaptive scaling for readable tile sizes.

### Sentiment Overlay
For a selected market, the app "pipes" market descriptions and recent comments (`polymarket comments list`) into the LLM (Moonshot API) to generate a 1-sentence **"Vibe Check."**

### Smart Alerts
A background watcher that triggers a cross-platform desktop notification if a specific market's price moves by >5% in an hour.

### Portfolio Snapshot
A secure view using `polymarket data value <address>` and `polymarket data positions` to show PnL in a clean table.

## User Commands

| Command | Description |
|---------|-------------|
| `polypulse dashboard` | Launch the interactive TUI heatmap |
| `polypulse search <query>` | Search markets by keyword |
| `polypulse watch <slug>` | Add a market to the high-priority monitor |
| `polypulse unwatch <slug>` | Remove a market from the monitor |
| `polypulse list` | Show all watched markets |
| `polypulse vibe <slug>` | Run an LLM sentiment analysis on a market |
| `polypulse portfolio` | Show portfolio PnL snapshot |
| `polypulse trade --auto` | *(Experimental)* Suggest trades based on volume spikes |

### Machine-Readable Output

Every command supports `--json` for structured output, making PolyPulse composable:

```bash
# Human-friendly
polypulse search "election"
# → Pretty table

# Machine-friendly
polypulse search "election" --json
# → {"markets": [{"slug": "...", "price": 0.65, "volume_24h": 123456}]}

polypulse vibe "some-market" --json
# → {"slug": "...", "sentiment": "bullish", "summary": "..."}
```

**Design principles for downstream clients:**
- Data on **stdout**, logs/errors on **stderr**
- Consistent exit codes: `0` success, `1` error, `2` config issue
- No interactive prompts in non-TUI commands — everything via flags
- Stable JSON schemas documented below

This means anyone can build a Telegram bot, Discord bot, web dashboard, or another agent skill that wraps `polypulse` — just like we wrap `polymarket-cli`.

## Configuration

Copy `config.example.json` to `config.json` and edit:

```json
{
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
    "sol"
  ]
}
```

| Setting | Description |
|---------|-------------|
| `watched_markets` | List of market slugs to monitor for alerts |
| `wallet_address` | Your wallet address for portfolio view |
| `alert_threshold_pct` | Price move % to trigger an alert (default: 5) |
| `alert_interval_seconds` | How often to check for alerts (default: 3600) |
| `refresh_interval_seconds` | Dashboard auto-refresh interval (default: 30) |
| `top_n_markets` | Number of markets shown in dashboard (default: 10) |
| `filter_patterns` | Case-insensitive patterns to hide markets (matched against slug and question) |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MOONSHOT_API_KEY` | For `vibe` command | Moonshot API key for LLM sentiment analysis |

## Agent Skills Support

PolyPulse ships as an [Agent Skills](https://agentskills.io/specification) compatible package. Any agent harness that supports the standard (pi, Claude Code, Codex, etc.) can load it:

```bash
# Add to your agent's skill path
~/.agents/skills/poly-pulse/
```

Or use it directly:
```
/skill:poly-pulse search "election"
```

The `SKILL.md` tells the agent how to install, configure, and use every command.

## Technical Constraints

- **Language:** Python (using [Textual](https://textual.textualize.io/) for the TUI)
- **CLI Framework:** [Click](https://click.palletsprojects.com/)
- **Integration:** Must not call the Polymarket API directly; wraps `polymarket-cli` commands. If the CLI updates its security or protocol, the app stays functional.
- **LLM:** Moonshot API via direct HTTP (`requests`)
- **Notifications:** Cross-platform via [plyer](https://github.com/kivy/plyer), fallback to console
- **State Management:** `config.json` for settings, `CLAUDE.md` for agent instructions
- **Filtering:** Configurable `filter_patterns` to exclude unwanted markets. Event deduplication to avoid showing multiple sub-markets from the same event.

## Testing

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_config.py
uv run pytest tests/test_polymarket.py
uv run pytest tests/test_alerts.py
uv run pytest tests/test_vibe.py
uv run pytest tests/test_cli.py

# Run a specific test class or method
uv run pytest tests/test_polymarket.py::TestFilterMarkets
uv run pytest tests/test_polymarket.py::TestDedupeByEvent::test_keeps_highest_volume_per_event
```

### Test Coverage

| File | Tests | Covers |
|------|-------|--------|
| `test_config.py` | 7 | Config load/save, watch list add/remove |
| `test_polymarket.py` | 21 | Market parsing, CLI wrapper, filtering, deduplication, search |
| `test_alerts.py` | 5 | Price snapshots, threshold triggers, callbacks |
| `test_vibe.py` | 4 | Prompt building, comment inclusion, error handling |
| `test_cli.py` | 7 | All CLI commands (watch, unwatch, list, trade, portfolio) |

All tests use mocks — no live `polymarket-cli` calls needed.

### TODO: Missing Tests
- **Treemap heatmap** — tile sizing, layout algorithm, color mapping
- **LLM sentiment** — actual LLM call, response parsing, error handling

## Roadmap

### Phase 1: PolyPulse CLI ← current
The core tool — filtered markets, heatmap, vibe checks, alerts, `--json` output.

### Phase 2: WhatsApp Bot
A conversational bot that wraps `polypulse --json`:
- **"what's moving?"** → top movers
- **"vibe election"** → LLM sentiment
- **"watch X"** → alerts pushed to your chat
- **"portfolio"** → PnL snapshot

Via Twilio WhatsApp API or Meta Cloud API.

### Phase 3: Additional Clients
- **Daily digest emailer** — Cron job: `polypulse search --json` + `polypulse vibe --json` → formatted HTML email every morning
- **Web dashboard** — Backend calls `polypulse --json`, serves a frontend with charts

### Other Possibilities
| Client | Description |
|--------|-------------|
| Telegram / Discord bot | Same as WhatsApp bot, different platform |
| Trading bot | Combines search + vibe data to suggest or place trades |
| Podcast / newsletter tool | Auto-generates weekly prediction market summaries |
| Multi-source aggregator | Wraps polypulse + Metaculus + Manifold into one unified view |
| Research tracker | Logs `--json` output to a database for academic analysis |

All of these are possible because PolyPulse exposes stable, machine-readable `--json` output on every command.

## License

MIT

## Architecture

```
polymarket-cli  →  polypulse  →  your app / bot / agent
```

PolyPulse is designed as a **composable middle layer**. It consumes `polymarket-cli` and exposes filtered, enriched, machine-readable data for anything built on top.
