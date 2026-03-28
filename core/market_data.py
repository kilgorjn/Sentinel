"""
Fetch global market index quotes from Finnhub and detect pre-market volatility.

The whole point of this module is to catch significant overnight moves in
European/Asian indices and US futures *before* the US market opens.

NOTE: MARKET_HOURS_ONLY in config does NOT affect market data fetching —
we always want to see overnight moves regardless of the polling schedule.

NOTE: Finnhub symbol format may differ from Yahoo Finance for indices.
If a quote returns c=0 and pc=0, the symbol is unrecognised or the market
is closed — we skip it rather than recording a spurious 0% change.
"""

import logging
import time
from datetime import datetime, timezone

import finnhub

from . import config

log = logging.getLogger(__name__)

# Lazy-initialised Finnhub client
_client: finnhub.Client | None = None


def _get_client() -> finnhub.Client | None:
    """Return a Finnhub client if an API key is configured, else None."""
    global _client
    if _client is None and config.FINNHUB_API_KEY:
        _client = finnhub.Client(api_key=config.FINNHUB_API_KEY)
    return _client


def fetch_snapshots() -> list[dict]:
    """
    Iterate over all tickers in config.MARKET_TICKERS, call the Finnhub
    quote endpoint for each, and return a list of snapshot dicts.

    Handles API errors gracefully (logs and skips individual tickers).
    Adds a small sleep between calls to respect the 60 calls/min rate limit.
    """
    client = _get_client()
    if client is None:
        log.debug("Finnhub not configured — skipping market data fetch")
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshots: list[dict] = []

    for region, tickers in config.MARKET_TICKERS.items():
        for name, symbol in tickers.items():
            try:
                quote = client.quote(symbol)

                # Finnhub quote fields: c (current), pc (prev close),
                # dp (percent change), h (high), l (low), t (timestamp)
                current_price = quote.get("c", 0)
                prev_close = quote.get("pc", 0)

                # Skip if quote returns all zeros — symbol not recognised
                # or market is closed with no data
                if current_price == 0 and prev_close == 0:
                    log.debug(
                        "Skipping %s (%s): quote returned zeros "
                        "(symbol invalid or market closed)",
                        name, symbol,
                    )
                    continue

                change_pct = quote.get("dp", 0.0)
                # Fallback: compute change_pct ourselves if dp is missing/zero
                if change_pct == 0 and prev_close != 0 and current_price != 0:
                    change_pct = round(
                        ((current_price - prev_close) / prev_close) * 100, 2
                    )

                snapshots.append({
                    "symbol": symbol,
                    "name": name,
                    "region": region,
                    "price": current_price,
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                    "high": quote.get("h"),
                    "low": quote.get("l"),
                    "fetched_at": now_iso,
                })

            except Exception as e:
                log.warning("Failed to fetch quote for %s (%s): %s", name, symbol, e)

            # Small delay to stay within 60 calls/min rate limit
            time.sleep(1.1)

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
