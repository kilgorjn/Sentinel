"""
Financial News Monitor — main entry point.

Normal mode:  python monitor.py
Test mode:    python monitor.py --test   (classifies built-in sample articles, no loop)
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from . import config
from . import feeds
from . import classifier
from . import spike_detector
from . import storage
from . import alerts
from . import migrations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("monitor")

# Sample articles for --test mode (cover the full severity range)
_TEST_ARTICLES = [
    {
        "title": "Federal Reserve Cuts Interest Rates by 50 Basis Points in Emergency Meeting",
        "summary": "The Federal Open Market Committee voted unanimously to cut the federal funds rate by 50 basis points to combat slowing economic growth.",
        "source": "Reuters",
        "url": "https://example.com/1",
        "published_at": datetime.now(timezone.utc),
    },
    {
        "title": "Apple Reports Record Quarterly Earnings, Beats Analyst Estimates",
        "summary": "Apple Inc. reported quarterly revenue of $124 billion, surpassing Wall Street expectations by 8%.",
        "source": "CNBC",
        "url": "https://example.com/2",
        "published_at": datetime.now(timezone.utc),
    },
    {
        "title": "Goldman Sachs Analyst Upgrades Ford to Buy",
        "summary": "Goldman Sachs raised its rating on Ford Motor Company from Hold to Buy with a $15 price target.",
        "source": "MarketWatch",
        "url": "https://example.com/3",
        "published_at": datetime.now(timezone.utc),
    },
    {
        "title": "S&P 500 Drops 4% as Inflation Data Shocks Markets",
        "summary": "US equities plunged after CPI data came in at 8.5%, well above the 7.9% forecast, raising fears of aggressive Fed action.",
        "source": "Bloomberg",
        "url": "https://example.com/4",
        "published_at": datetime.now(timezone.utc),
    },
    {
        "title": "Fed Expected to Hold Rates Steady at Next Meeting, Sources Say",
        "summary": "Federal Reserve officials are likely to pause rate increases at the upcoming FOMC meeting, according to people familiar with the matter.",
        "source": "WSJ",
        "url": "https://example.com/5",
        "published_at": datetime.now(timezone.utc),
    },
]


def _is_market_hours() -> bool:
    """Return True during US market hours: 09:00–17:00 ET, Mon–Fri."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:  # Sat/Sun
        return False
    return 9 <= now_et.hour < 17


def process_articles(article_list: list[dict], detector: spike_detector.SpikeDetector) -> None:
    """Classify each article, store it, alert if needed, update spike detector."""
    for article in article_list:
        title = article.get("title", "")

        # Skip if we've already logged this title in the past 24 hours
        if storage.already_seen(title):
            log.debug("Skipping already-seen: %s", title)
            continue

        result = classifier.classify(article)
        level  = result.get("classification", "LOW")

        # Print to console
        alerts.alert_article(article, result)

        # Persist
        storage.save_event(article, result)

        # Check for surge
        is_new_surge = detector.record(article, level)
        if is_new_surge:
            alerts.alert_surge(
                count=detector.current_count(),
                recent_titles=detector.recent_events(),
                window_minutes=config.SPIKE_WINDOW_MINUTES,
            )

        # Small gap between Ollama calls to avoid hammering the GPU
        time.sleep(0.5)


def run_test_mode() -> None:
    """Classify the built-in sample articles and exit — useful for smoke-testing."""
    print("\n" + "=" * 60)
    print("  FINANCIAL NEWS MONITOR — TEST MODE")
    print(f"  Ollama: {config.OLLAMA_URL}  model: {config.OLLAMA_MODEL}")
    print("=" * 60 + "\n")

    detector = spike_detector.SpikeDetector()
    process_articles(_TEST_ARTICLES, detector)

    print("\n--- 24h Summary ---")
    for row in storage.summary():
        print(f"  {row['classification']:<8} {row['count']}")
    print()


def run_monitor() -> None:
    """Main polling loop."""
    log.info("Starting financial news monitor")
    log.info("Ollama: %s  model: %s", config.OLLAMA_URL, config.OLLAMA_MODEL)
    log.info("Poll interval: %ds  Spike window: %dmin  Threshold: %d HIGH events",
             config.POLL_INTERVAL_SECONDS, config.SPIKE_WINDOW_MINUTES, config.SPIKE_HIGH_THRESHOLD)

    detector = spike_detector.SpikeDetector()

    while True:
        try:
            # Market data — always runs (catches overnight moves)
            if config.MARKET_DATA_ENABLED:
                try:
                    from core import market_data
                    snapshots = market_data.fetch_snapshots()
                    if snapshots:
                        storage.save_snapshots(snapshots)
                        signals = market_data.detect_volatility(snapshots)
                        for signal in signals:
                            if signal["severity"] == "HIGH":
                                # Create a synthetic article dict so spike_detector can process it
                                synthetic = {
                                    "title": signal["message"],
                                    "source": f"Market Data ({signal['region'].title()})",
                                    "published_at": datetime.now(timezone.utc),
                                }
                                is_surge = detector.record(synthetic, "HIGH")
                                alerts.alert_market_signal(signal)
                                if is_surge:
                                    alerts.alert_surge(
                                        count=detector.current_count(),
                                        recent_titles=detector.recent_events(),
                                        window_minutes=config.SPIKE_WINDOW_MINUTES,
                                    )
                except Exception as e:
                    log.error("Market data fetch failed: %s", e, exc_info=True)

            # News fetch — gated by market hours if configured
            if config.MARKET_HOURS_ONLY and not _is_market_hours():
                log.debug("Outside market hours — skipping news fetch")
            else:
                log.info("--- Fetching news ---")
                article_list = feeds.fetch_all()
                process_articles(article_list, detector)

            # Periodic summary
            rows = storage.summary()
            counts = {r["classification"]: r["count"] for r in rows}
            market_msg = ""
            if config.MARKET_DATA_ENABLED:
                market_snapshots = storage.get_latest_market_data()
                if market_snapshots:
                    market_msg = f"  | Market tickers tracked: {len(market_snapshots)}"
            log.info(
                "24h totals — HIGH:%d  MEDIUM:%d  LOW:%d  | Surge window: %d/%d%s",
                counts.get("HIGH", 0),
                counts.get("MEDIUM", 0),
                counts.get("LOW", 0),
                detector.current_count(),
                config.SPIKE_HIGH_THRESHOLD,
                market_msg,
            )

        except KeyboardInterrupt:
            log.info("Interrupted — shutting down.")
            sys.exit(0)
        except Exception as e:
            log.error("Unexpected error in main loop: %s", e, exc_info=True)

        time.sleep(config.POLL_INTERVAL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Financial news monitor with Ollama classification")
    parser.add_argument("--test", action="store_true", help="Classify sample articles and exit")
    args = parser.parse_args()

    # Initialize database and run migrations
    storage.initialize()
    if not migrations.migrate_from_sqlite():
        log.error("SQLite migration failed — aborting startup.")
        sys.exit(1)

    if args.test:
        run_test_mode()
    else:
        run_monitor()


if __name__ == "__main__":
    main()
