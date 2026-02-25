"""PolyPulse CLI — all user-facing commands."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

import os

from polypulse.config import add_watch, load_config, remove_watch
from polypulse.polymarket import (
    dedupe_by_event,
    fetch_active_markets,
    fetch_market,
    filter_markets,
    search_markets,
    fetch_comments,
)
from polypulse.vibe import run_vibe

console = Console(stderr=True)
out = Console()


def _output_json(data, file=None):
    """Write JSON to stdout."""
    click.echo(json.dumps(data, indent=2), file=file)


def _output_table(title: str, markets, columns=None):
    """Render a Rich table to stdout."""
    table = Table(title=title, show_lines=True)
    cols = columns or ["Slug", "Question", "Price", "24h Vol", "1d Δ"]
    for c in cols:
        table.add_column(c)
    for m in markets:
        price = f"{m.outcome_prices[0]:.3f}" if m.outcome_prices else "?"
        change = f"{m.one_day_price_change:+.3f}" if m.one_day_price_change is not None else "?"
        table.add_row(
            m.slug,
            m.question[:60],
            price,
            f"${m.volume_24h:,.0f}",
            change,
        )
    out.print(table)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="polypulse")
def cli():
    """PolyPulse — the smart terminal layer for Polymarket."""


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@cli.command()
def dashboard():
    """Launch the interactive TUI heatmap."""
    from polypulse.dashboard import run_dashboard
    run_dashboard()


@cli.command()
@click.argument("query")
@click.option("--limit", default=10, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def search(query, limit, as_json):
    """Search markets by keyword."""
    try:
        markets = search_markets(query, limit=limit)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}", highlight=False)
        sys.exit(1)

    if as_json:
        _output_json({"markets": [m.to_dict() for m in markets]})
    else:
        _output_table(f"Search: {query}", markets)


# ---------------------------------------------------------------------------
# watch / unwatch / list
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def watch(slug, as_json):
    """Add a market to the watch list."""
    config = add_watch(slug)
    if as_json:
        _output_json({"watched_markets": config["watched_markets"]})
    else:
        console.print(f"[green]✓[/green] Watching [bold]{slug}[/bold]")


@cli.command()
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def unwatch(slug, as_json):
    """Remove a market from the watch list."""
    config = remove_watch(slug)
    if as_json:
        _output_json({"watched_markets": config["watched_markets"]})
    else:
        console.print(f"[yellow]✗[/yellow] Unwatched [bold]{slug}[/bold]")


@cli.command("list")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def list_watched(as_json):
    """Show all watched markets."""
    config = load_config()
    watched = config["watched_markets"]
    if as_json:
        _output_json({"watched_markets": watched})
    else:
        if not watched:
            console.print("[dim]No watched markets. Use [bold]polypulse watch <slug>[/bold] to add one.[/dim]")
        else:
            for slug in watched:
                console.print(f"  • {slug}")


# ---------------------------------------------------------------------------
# vibe
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def vibe(slug, as_json):
    """Run LLM sentiment analysis on a market."""
    try:
        market = fetch_market(slug)
    except Exception as e:
        console.print(f"[red]Error fetching market:[/red] {e}", highlight=False)
        sys.exit(1)

    # Try to get comments for richer context
    comments = []
    if market.event_slug:
        try:
            # Fetch comments using the event
            events_raw = json.loads(
                __import__("polypulse.polymarket", fromlist=["run_polymarket"]).run_polymarket(
                    "markets", "get", slug
                )
            )
            event_id = None
            evts = events_raw.get("events", [])
            if evts:
                event_id = evts[0].get("id")
            if event_id:
                comments = fetch_comments("event", str(event_id), limit=10)
        except Exception:
            pass  # Comments are optional enrichment

    try:
        result = run_vibe(market, comments or None)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}", highlight=False)
        sys.exit(2)
    except Exception as e:
        console.print(f"[red]LLM Error:[/red] {e}", highlight=False)
        sys.exit(1)

    if as_json:
        _output_json(result)
    else:
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(
            result["sentiment"], "❓"
        )
        console.print(f"{emoji} [bold]{result['sentiment'].upper()}[/bold]: {result['summary']}")


# ---------------------------------------------------------------------------
# portfolio
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def portfolio(as_json):
    """Show portfolio PnL snapshot."""
    config = load_config()
    wallet = config.get("wallet_address", "")
    if not wallet:
        console.print("[red]Error:[/red] No wallet_address in config.json", highlight=False)
        sys.exit(2)

    from polypulse.polymarket import run_polymarket

    try:
        value_raw = run_polymarket("data", "value", wallet)
        positions_raw = run_polymarket("data", "positions", wallet)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}", highlight=False)
        sys.exit(1)

    value_data = json.loads(value_raw)
    positions_data = json.loads(positions_raw)

    if as_json:
        _output_json({"wallet": wallet, "value": value_data, "positions": positions_data})
    else:
        console.print(f"[bold]Wallet:[/bold] {wallet}")
        console.print(f"[bold]Value:[/bold] {json.dumps(value_data)}")
        if isinstance(positions_data, list):
            table = Table(title="Positions", show_lines=True)
            # Auto-detect columns from first position
            if positions_data:
                for key in positions_data[0]:
                    table.add_column(key)
                for pos in positions_data:
                    table.add_row(*[str(v) for v in pos.values()])
            out.print(table)
        else:
            console.print(f"[bold]Positions:[/bold] {json.dumps(positions_data)}")


# ---------------------------------------------------------------------------
# trade
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--auto", is_flag=True, help="Suggest trades based on volume spikes.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def trade(auto, as_json):
    """(Experimental) Suggest trades based on volume spikes."""
    if not auto:
        console.print("[dim]Use --auto to get trade suggestions.[/dim]")
        return

    config = load_config()
    try:
        markets = fetch_active_markets(limit=50)
        markets = filter_markets(markets, config.get("filter_patterns", []))
        markets = dedupe_by_event(markets)
        # Sort by 24h volume, pick top movers
        markets.sort(key=lambda m: m.volume_24h, reverse=True)
        top = markets[:5]
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}", highlight=False)
        sys.exit(1)

    suggestions = []
    for m in top:
        direction = "BUY" if (m.one_day_price_change or 0) > 0 else "WATCH"
        suggestions.append({
            "slug": m.slug,
            "question": m.question,
            "price": m.outcome_prices[0] if m.outcome_prices else None,
            "volume_24h": m.volume_24h,
            "signal": direction,
        })

    if as_json:
        _output_json({"suggestions": suggestions})
    else:
        table = Table(title="Trade Suggestions (Experimental)", show_lines=True)
        table.add_column("Signal")
        table.add_column("Slug")
        table.add_column("Price")
        table.add_column("24h Vol")
        for s in suggestions:
            color = "green" if s["signal"] == "BUY" else "yellow"
            table.add_row(
                f"[{color}]{s['signal']}[/{color}]",
                s["slug"],
                f"{s['price']:.3f}" if s["price"] else "?",
                f"${s['volume_24h']:,.0f}",
            )
        out.print(table)


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--preview", is_flag=True, help="Print HTML to stdout, don't send.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def digest(preview, as_json):
    """Generate and send the daily digest email."""
    from polypulse.digest import fetch_digest_data, render_html, send_email

    config = load_config()

    try:
        data = fetch_digest_data()
    except Exception as e:
        console.print(f"[red]Error gathering digest data:[/red] {e}", highlight=False)
        sys.exit(1)

    if as_json:
        _output_json(data)
        return

    html = render_html(data)

    if preview:
        click.echo(html)
        return

    # Send email
    smtp_host = config.get("smtp_host", os.environ.get("POLYPULSE_SMTP_HOST", "smtp.gmail.com"))
    smtp_port = config.get("smtp_port", int(os.environ.get("POLYPULSE_SMTP_PORT", "587")))
    smtp_user = config.get("smtp_user", os.environ.get("POLYPULSE_SMTP_USER", ""))
    smtp_password = config.get("smtp_password", os.environ.get("POLYPULSE_SMTP_PASSWORD", ""))
    recipient = config.get("digest_recipient", os.environ.get("POLYPULSE_DIGEST_RECIPIENT", ""))

    if not recipient:
        console.print("[red]Error:[/red] No digest_recipient in config.json or POLYPULSE_DIGEST_RECIPIENT env var.", highlight=False)
        sys.exit(2)

    try:
        send_email(html, recipient, smtp_host=smtp_host, smtp_port=smtp_port,
                   smtp_user=smtp_user, smtp_password=smtp_password)
        console.print(f"[green]✓[/green] Digest sent to [bold]{recipient}[/bold]")
    except Exception as e:
        console.print(f"[red]Error sending email:[/red] {e}", highlight=False)
        sys.exit(1)
