"""
Fetch global market index quotes from Yahoo Finance and detect pre-market volatility.

The whole point of this module is to catch significant overnight moves in
European/Asian indices and US futures *before* the US market opens.

NOTE: MARKET_HOURS_ONLY in config does NOT affect market data fetching —
we always want to see overnight moves regardless of the polling schedule.

Uses yfinance (no API key required). If a ticker returns no price data
(market closed or invalid symbol), it is skipped.
"""

import logging
import time
from datetime import datetime, timezone

import yfinance as yf

from . import config

log = logging.getLogger(__name__)


def fetch_snapshots() -> list[dict]:
    """
    Iterate over all tickers in config.MARKET_TICKERS, use yfinance
    fast_info for each, and return a list of snapshot dicts.

    Handles errors gracefully (logs and skips individual tickers).
    Adds a 0.5s sleep between calls to be polite to Yahoo's servers.
    """
    if not config.MARKET_DATA_ENABLED:
        log.debug("Market data disabled — skipping fetch")
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshots: list[dict] = []

    for region, tickers in config.MARKET_TICKERS.items():
        for name, symbol in tickers.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                price = info.last_price
                prev_close = info.previous_close

                if not price or not prev_close or price == 0 or prev_close == 0:
                    log.debug("Skipping %s (%s): no price data", name, symbol)
                    continue

                change_pct = round(((price - prev_close) / prev_close) * 100, 2)

                snapshots.append({
                    "symbol": symbol,
                    "name": name,
                    "region": region,
                    "price": price,
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                    "high": None,
                    "low": None,
                    "fetched_at": now_iso,
                })

            except Exception as e:
                log.warning("Failed to fetch quote for %s (%s): %s", name, symbol, e)

            time.sleep(0.5)

    log.info("Fetched %d market snapshots", len(snapshots))
    return snapshots


def detect_volatility(snapshots: list[dict]) -> list[dict]:
    """
    Check each snapshot against volatility thresholds and look for
    cross-market correlation (3+ indices across different regions all
    moving >1% in the same direction).

    Returns a list of volatility signal dicts.
    """
    signals: list[dict] = []

    for snap in snapshots:
        pct = abs(snap.get("change_pct", 0))
        if pct >= config.MARKET_VOLATILITY_HIGH:
            severity = "HIGH"
        elif pct >= config.MARKET_VOLATILITY_MEDIUM:
            severity = "MEDIUM"
        else:
            continue

        direction = "up" if snap["change_pct"] > 0 else "down"
        signals.append({
            "type": "index_move",
            "severity": severity,
            "symbol": snap["symbol"],
            "name": snap["name"],
            "region": snap["region"],
            "change_pct": snap["change_pct"],
            "message": (
                f"{snap['name']} {direction} {abs(snap['change_pct']):.1f}% "
                f"— {'significant' if severity == 'HIGH' else 'notable'} "
                f"overnight move"
            ),
        })

    # Cross-market correlation check:
    # If 3+ indices across different regions are all moving >1% in the
    # same direction, flag it as a global signal.
    up_regions: set[str] = set()
    down_regions: set[str] = set()
    up_names: list[str] = []
    down_names: list[str] = []

    for snap in snapshots:
        pct = snap.get("change_pct", 0)
        if pct > config.MARKET_VOLATILITY_MEDIUM:
            up_regions.add(snap["region"])
            up_names.append(snap["name"])
        elif pct < -config.MARKET_VOLATILITY_MEDIUM:
            down_regions.add(snap["region"])
            down_names.append(snap["name"])

    if len(up_names) >= 3 and len(up_regions) >= 2:
        signals.append({
            "type": "cross_market_correlation",
            "severity": "HIGH",
            "symbol": None,
            "name": None,
            "region": "global",
            "change_pct": max(s["change_pct"] for s in snapshots),
            "message": (
                f"Global rally: {len(up_names)} indices up >1% across "
                f"{', '.join(sorted(up_regions))} — correlated bullish move"
            ),
        })

    if len(down_names) >= 3 and len(down_regions) >= 2:
        signals.append({
            "type": "cross_market_correlation",
            "severity": "HIGH",
            "symbol": None,
            "name": None,
            "region": "global",
            "change_pct": min(s["change_pct"] for s in snapshots),
            "message": (
                f"Global sell-off: {len(down_names)} indices down >1% across "
                f"{', '.join(sorted(down_regions))} — correlated bearish move"
            ),
        })

    return signals


def get_latest_snapshots() -> list[dict]:
    """Query the DB for the most recent snapshot per ticker (for the API)."""
    from . import storage
    return storage.get_latest_market_data()
