"""WhatsApp bot — Twilio webhook server wrapping polypulse --json."""

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

# Command keywords mapped to (command_name, expects_argument)
_COMMANDS = [
    (["movers", "moving", "what's moving", "top", "hot"], "movers", False),
    (["vibe"], "vibe", True),
    (["watch"], "watch", True),
    (["unwatch"], "unwatch", True),
    (["list", "watchlist"], "list", False),
    (["search", "find"], "search", True),
    (["portfolio", "pnl", "positions"], "portfolio", False),
    (["help", "?", "hi", "hello"], "help", False),
]


def parse_intent(message: str) -> tuple[str, str]:
    """Parse a WhatsApp message into (command, argument).

    Examples:
        "what's moving" → ("movers", "")
        "vibe gta-6" → ("vibe", "gta-6")
        "search election" → ("search", "election")
        "watch some-slug" → ("watch", "some-slug")
        "random nonsense" → ("help", "")
    """
    text = message.strip().lower()

    for keywords, command, expects_arg in _COMMANDS:
        for kw in keywords:
            if text == kw:
                return (command, "")
            if expects_arg and text.startswith(kw + " "):
                arg = message.strip()[len(kw) + 1:].strip()
                return (command, arg)
            if not expects_arg and kw in text:
                return (command, "")

    return ("help", "")


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------

_HELP_TEXT = """📊 *PolyPulse Bot*

Commands:
• *movers* — top markets by 24h volume
• *vibe <slug>* — AI sentiment analysis
• *search <query>* — search markets
• *watch <slug>* — add to watch list
• *unwatch <slug>* — remove from watch list
• *list* — show watched markets
• *portfolio* — PnL snapshot
• *help* — this message"""

_MAX_LEN = 4000  # WhatsApp limit is 4096, leave room


def format_response(command: str, data) -> str:
    """Format polypulse --json output as WhatsApp-friendly text."""
    if command == "help":
        return _HELP_TEXT

    if command == "movers":
        suggestions = data.get("suggestions", [])
        if not suggestions:
            return "No movers found right now."
        lines = ["🔥 *Top Movers*", ""]
        for i, s in enumerate(suggestions, 1):
            emoji = "📈" if s.get("signal") == "BUY" else "👀"
            price = f"{s['price']:.3f}" if s.get("price") is not None else "?"
            vol = _fmt_vol(s.get("volume_24h", 0))
            lines.append(f"{i}. {emoji} {s.get('question', s.get('slug', '?'))}")
            lines.append(f"   Price: {price} · Vol: {vol}")
        return _truncate("\n".join(lines))

    if command == "vibe":
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(
            data.get("sentiment", ""), "❓"
        )
        return (
            f"{emoji} *{data.get('sentiment', '?').upper()}*\n"
            f"_{data.get('slug', '?')}_\n\n"
            f"{data.get('summary', 'No summary available.')}"
        )

    if command == "search":
        markets = data.get("markets", [])
        if not markets:
            return "No results found."
        lines = ["🔍 *Search Results*", ""]
        for m in markets[:10]:
            price = m.get("outcome_prices", [None])[0]
            price_str = f"{price:.3f}" if price is not None else "?"
            vol = _fmt_vol(m.get("volume_24h", 0))
            lines.append(f"• {m.get('question', m.get('slug', '?'))}")
            lines.append(f"  `{m.get('slug', '?')}` · {price_str} · {vol}")
        return _truncate("\n".join(lines))

    if command == "watch":
        slugs = data.get("watched_markets", [])
        return f"✅ Watching! ({len(slugs)} total)"

    if command == "unwatch":
        slugs = data.get("watched_markets", [])
        return f"✅ Unwatched. ({len(slugs)} remaining)"

    if command == "list":
        slugs = data.get("watched_markets", [])
        if not slugs:
            return "No watched markets. Send *watch <slug>* to add one."
        lines = ["👁 *Watch List*", ""]
        for s in slugs:
            lines.append(f"• `{s}`")
        return "\n".join(lines)

    if command == "portfolio":
        wallet = data.get("wallet", "?")
        positions = data.get("positions", [])
        value = data.get("value", {})
        lines = [f"💰 *Portfolio*", f"Wallet: `{wallet[:10]}...{wallet[-6:]}`"]
        if isinstance(value, dict):
            for k, v in value.items():
                lines.append(f"{k}: {v}")
        if isinstance(positions, list) and positions:
            lines.append(f"\n{len(positions)} position(s)")
            for p in positions[:5]:
                lines.append(f"• {p.get('market', '?')} — {p.get('pnl', '?')}")
        return _truncate("\n".join(lines))

    return _HELP_TEXT


def _fmt_vol(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def _truncate(text: str) -> str:
    if len(text) <= _MAX_LEN:
        return text
    return text[:_MAX_LEN - 20] + "\n\n_(truncated)_"


# ---------------------------------------------------------------------------
# Polypulse subprocess runner
# ---------------------------------------------------------------------------

def _run_polypulse(*args: str) -> dict | list:
    """Run a polypulse CLI command with --json and return parsed output."""
    polypulse_bin = Path(sys.executable).parent / "polypulse"
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + ":" + os.environ.get("PATH", "")}
    cmd = [str(polypulse_bin), *args, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"polypulse {' '.join(args)} failed")
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

def handle_message(message: str) -> str:
    """Parse intent, run polypulse, return formatted reply."""
    command, arg = parse_intent(message)

    if command == "help":
        return format_response("help", {})

    try:
        if command == "movers":
            data = _run_polypulse("trade", "--auto")
        elif command == "vibe":
            if not arg:
                return "Usage: *vibe <slug>*\nExample: vibe will-gta-6-cost-100"
            data = _run_polypulse("vibe", arg)
        elif command == "search":
            if not arg:
                return "Usage: *search <query>*\nExample: search election"
            data = _run_polypulse("search", arg)
        elif command == "watch":
            if not arg:
                return "Usage: *watch <slug>*\nExample: watch will-gta-6-cost-100"
            data = _run_polypulse("watch", arg)
        elif command == "unwatch":
            if not arg:
                return "Usage: *unwatch <slug>*"
            data = _run_polypulse("unwatch", arg)
        elif command == "list":
            data = _run_polypulse("list")
        elif command == "portfolio":
            data = _run_polypulse("portfolio")
        else:
            return format_response("help", {})
    except Exception as e:
        return f"❌ Error: {e}"

    return format_response(command, data)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

def create_bot_app() -> Flask:
    """Create the WhatsApp bot Flask app."""
    app = Flask(__name__)

    @app.route("/webhook", methods=["POST"])
    def webhook():
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")

        reply_text = handle_message(incoming_msg)

        resp = MessagingResponse()
        resp.message(reply_text)
        return str(resp), 200, {"Content-Type": "text/xml"}

    @app.route("/health")
    def health():
        return "OK"

    return app


def run_bot(port: int = 5000) -> None:
    """Load .env, print setup instructions, start the bot server."""
    load_dotenv()

    # Validate config
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    number = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")

    missing = []
    if not sid:
        missing.append("TWILIO_ACCOUNT_SID")
    if not token:
        missing.append("TWILIO_AUTH_TOKEN")
    if not number:
        missing.append("TWILIO_WHATSAPP_NUMBER")

    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}")
        print(f"   Set them in .env or export them.")
        sys.exit(2)

    print(f"📱 PolyPulse WhatsApp Bot")
    print(f"   Twilio number: {number}")
    print(f"   Server: http://localhost:{port}")
    print()
    print(f"   Next steps:")
    print(f"   1. In another terminal: ngrok http {port}")
    print(f"   2. Copy the ngrok https URL")
    print(f"   3. In Twilio Console → Messaging → WhatsApp Sandbox → Configuration")
    print(f"      Set webhook to: <ngrok-url>/webhook")
    print(f"   4. Send a WhatsApp message to your sandbox number!")
    print()

    app = create_bot_app()
    app.run(host="127.0.0.1", port=port, debug=False)
