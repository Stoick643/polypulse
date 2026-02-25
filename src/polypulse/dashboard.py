"""TUI Dashboard — Textual-based treemap heatmap of top markets."""

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static
from textual.widget import Widget
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

from polypulse.config import load_config
from polypulse.polymarket import (
    dedupe_by_event,
    fetch_active_markets,
    filter_markets,
    Market,
)
from polypulse.scaling import pick_scale
from polypulse.treemap import Rect, layout_treemap


# Color palette — bright, high contrast for terminal readability
_COLORS = {
    "hot_up": Style(color="white", bgcolor="bright_green"),
    "up": Style(color="white", bgcolor="green"),
    "flat": Style(color="black", bgcolor="bright_yellow"),
    "down": Style(color="white", bgcolor="red"),
    "hot_down": Style(color="white", bgcolor="bright_red"),
    "other": Style(color="white", bgcolor="blue"),
    "border_v": Style(color="grey23", bgcolor="grey23"),
    "border_h": Style(color="grey23", bgcolor="grey23"),
}


def _tile_style(market: Market | None) -> Style:
    if market is None:
        return _COLORS["other"]
    change = market.one_day_price_change or 0
    if change > 0.05:
        return _COLORS["hot_up"]
    elif change > 0.01:
        return _COLORS["up"]
    elif change > -0.01:
        return _COLORS["flat"]
    elif change > -0.05:
        return _COLORS["down"]
    return _COLORS["hot_down"]


def _format_vol(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    elif v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


class TreemapWidget(Widget):
    """Renders a treemap filling its entire area."""

    DEFAULT_CSS = """
    TreemapWidget {
        width: 1fr;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._markets: list[Market] = []
        self._others_vol: float = 0.0
        self._scaled_volumes: list[float] | None = None

    def set_data(
        self,
        markets: list[Market],
        others_vol: float = 0.0,
        scaled_volumes: list[float] | None = None,
    ) -> None:
        self._markets = markets
        self._others_vol = others_vol
        self._scaled_volumes = scaled_volumes
        self.refresh()

    def render_line(self, y: int) -> Strip:
        w = self.size.width
        h = self.size.height
        if not self._markets or w == 0 or h == 0:
            return Strip([Segment(" " * w)])

        # Build values list: use scaled volumes if available
        if self._scaled_volumes:
            values = list(self._scaled_volumes)
        else:
            values = [m.volume_24h for m in self._markets]
        has_others = self._others_vol > 0
        if has_others:
            # Others tile gets the minimum scaled value so it's visible but small
            others_scaled = min(values) * 0.5 if values else 1.0
            values.append(others_scaled)

        rects = layout_treemap(values, Rect(0, 0, w, h))

        # Build a grid row: for each x, find which rect contains (x, y)
        segments: list[Segment] = []
        x = 0
        while x < w:
            # Find the rect at (x, y)
            tile_idx = None
            rect = None
            for i, r in enumerate(rects):
                if r.x <= x < r.x + r.w and r.y <= y < r.y + r.h:
                    tile_idx = i
                    rect = r
                    break

            if tile_idx is None or rect is None:
                segments.append(Segment(" "))
                x += 1
                continue

            # How many chars until we leave this rect?
            run = min(rect.x + rect.w - x, w - x)

            # Determine market and style
            is_others = has_others and tile_idx == len(self._markets)
            if is_others:
                market = None
                style = _COLORS["other"]
            else:
                market = self._markets[tile_idx]
                style = _tile_style(market)

            # What line within the tile is this?
            local_y = y - rect.y
            local_h = rect.h

            # Draw border on edges
            is_bottom = (local_y == local_h - 1)
            is_top = (local_y == 0)

            if is_top or is_bottom:
                # Horizontal border
                border_style = Style(color="grey30", bgcolor=style.bgcolor)
                if run >= 2:
                    line = "─" * run
                else:
                    line = " " * run
                segments.append(Segment(line, border_style))
            else:
                # Content area with vertical border chars
                inner_w = max(run - 2, 0)
                content = self._tile_line(market, local_y - 1, local_h - 2, inner_w, is_others)

                border_style = Style(color="grey30", bgcolor=style.bgcolor)
                if run >= 2:
                    segments.append(Segment("│", border_style))
                    segments.append(Segment(content, style))
                    segments.append(Segment("│", border_style))
                else:
                    segments.append(Segment(content[:run], style))

            x += run

        return Strip(segments)

    def _tile_line(
        self, market: Market | None, line: int, avail_h: int, w: int, is_others: bool
    ) -> str:
        """Return one content line for a tile, padded/truncated to w chars."""
        if w <= 0:
            return ""

        if is_others:
            texts = [
                "Others (combined)",
                _format_vol(self._others_vol),
            ]
        elif market is None:
            texts = [""]
        else:
            price = market.outcome_prices[0] if market.outcome_prices else 0
            change = market.one_day_price_change or 0
            emoji = "▲" if change > 0.01 else ("▼" if change < -0.01 else "●")
            texts = [
                f"{emoji} {market.question}",
                f"Price: {price:.2f}  {change:+.1%}",
                f"Vol: {_format_vol(market.volume_24h)}",
            ]

        if line < 0 or line >= len(texts):
            return " " * w

        text = f" {texts[line]}"
        if len(text) > w:
            text = text[: w - 1] + "…"
        return text.ljust(w)

    def get_content_height(self, container, viewport, width):
        return self.size.height


class DashboardApp(App):
    """PolyPulse TUI Dashboard."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #status {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Loading...", id="status")
        yield TreemapWidget(id="heatmap")
        yield Footer()

    def on_mount(self) -> None:
        self.config = load_config()
        self.action_refresh()
        interval = self.config.get("refresh_interval_seconds", 30)
        self.set_interval(interval, self.action_refresh)

    def action_refresh(self) -> None:
        """Fetch and display markets."""
        status = self.query_one("#status", Static)
        status.update("Refreshing...")

        try:
            top_n = self.config.get("top_n_markets", 10)
            patterns = self.config.get("filter_patterns", [])

            markets = fetch_active_markets(limit=200)
            markets = filter_markets(markets, patterns)
            markets = dedupe_by_event(markets)
            markets.sort(key=lambda m: m.volume_24h, reverse=True)

            # Top N candidates
            top = markets[:top_n]
            volumes = [m.volume_24h for m in top]

            # Adaptive power scaling: finds exponent p so that
            # max_area / min_area ≈ 7. Trims up to 2 smallest first.
            scaled, removed_indices, exponent = pick_scale(volumes)

            # Move removed markets into "Others" bucket
            kept = [m for i, m in enumerate(top) if i not in removed_indices]
            others_vol = (
                sum(m.volume_24h for m in markets[top_n:])
                + sum(top[i].volume_24h for i in removed_indices)
            )

            heatmap = self.query_one("#heatmap", TreemapWidget)
            heatmap.set_data(kept, others_vol, scaled_volumes=scaled)

            scale_info = "raw" if exponent == 1.0 else f"p={exponent}"
            status.update(
                f"Top {len(kept)} markets by 24h volume ({scale_info})  |  "
                f"r: refresh  q: quit"
            )
        except Exception as e:
            status.update(f"Error: {e}")


def run_dashboard() -> None:
    """Launch the TUI dashboard."""
    app = DashboardApp()
    app.run()
