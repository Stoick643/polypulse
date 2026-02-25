"""Smart alerts — background price monitoring with notifications."""

import sys
import time
from typing import Callable

from polypulse.polymarket import fetch_market, Market


def _notify(title: str, message: str) -> None:
    """Send a desktop notification, falling back to console."""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            timeout=10,
        )
    except Exception:
        print(f"[ALERT] {title}: {message}", file=sys.stderr)


# In-memory price snapshots: slug -> (timestamp, price)
_snapshots: dict[str, tuple[float, float]] = {}


def record_snapshot(slug: str, price: float, timestamp: float | None = None) -> None:
    """Record a price snapshot for a market."""
    _snapshots[slug] = (timestamp or time.time(), price)


def get_snapshot(slug: str) -> tuple[float, float] | None:
    """Get the last recorded (timestamp, price) for a slug, or None."""
    return _snapshots.get(slug)


def clear_snapshots() -> None:
    """Clear all recorded snapshots."""
    _snapshots.clear()


def check_alert(
    slug: str,
    current_price: float,
    threshold_pct: float = 5.0,
    callback: Callable[[str, float, float, float], None] | None = None,
) -> bool:
    """Check if a market's price moved beyond threshold since last snapshot.

    Args:
        slug: Market slug.
        current_price: Current price.
        threshold_pct: Percentage threshold to trigger alert.
        callback: Optional function(slug, old_price, new_price, change_pct).

    Returns:
        True if alert was triggered, False otherwise.
    """
    prev = get_snapshot(slug)
    if prev is None:
        record_snapshot(slug, current_price)
        return False

    _, old_price = prev
    if old_price == 0:
        record_snapshot(slug, current_price)
        return False

    change_pct = abs((current_price - old_price) / old_price) * 100

    if change_pct >= threshold_pct:
        if callback:
            callback(slug, old_price, current_price, change_pct)
        else:
            direction = "📈" if current_price > old_price else "📉"
            _notify(
                f"PolyPulse Alert {direction}",
                f"{slug}: {old_price:.3f} → {current_price:.3f} ({change_pct:+.1f}%)",
            )
        # Reset snapshot after alert
        record_snapshot(slug, current_price)
        return True

    return False


def run_alert_loop(
    slugs: list[str],
    threshold_pct: float = 5.0,
    interval_seconds: int = 3600,
    callback: Callable[[str, float, float, float], None] | None = None,
    max_iterations: int | None = None,
) -> None:
    """Run the alert watcher loop.

    Args:
        slugs: List of market slugs to monitor.
        threshold_pct: Alert threshold percentage.
        interval_seconds: Seconds between checks.
        callback: Optional alert callback.
        max_iterations: Stop after N iterations (None = forever).
    """
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        for slug in slugs:
            try:
                market = fetch_market(slug)
                price = market.outcome_prices[0] if market.outcome_prices else 0.0
                check_alert(slug, price, threshold_pct, callback)
            except Exception as e:
                print(f"[WARN] Error checking {slug}: {e}", file=sys.stderr)

        iteration += 1
        if max_iterations is None or iteration < max_iterations:
            time.sleep(interval_seconds)
