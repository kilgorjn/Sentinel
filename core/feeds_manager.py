"""Manage RSS feeds stored in SQLite database."""

import logging
import uuid
from pathlib import Path
from typing import Optional

from . import storage

log = logging.getLogger(__name__)

_DEFAULT_FEED_TYPE = "RSS 2.0"

# Path to old feeds.json (for migration)
_FEEDS_JSON = Path(__file__).resolve().parent.parent / "feeds.json"


def _migrate_feeds_from_json() -> None:
    """Migrate feeds from old feeds.json file to SQLite database (one-time operation)."""
    if not _FEEDS_JSON.exists():
        return

    # Check if feeds already exist in DB
    existing = storage.load_feeds(active_only=False)
    if existing:
        log.debug("Feeds already exist in database, skipping JSON migration")
        return

    # Migrate feeds from JSON to DB
    try:
        import json
        data = json.loads(_FEEDS_JSON.read_text())
        feeds = data.get("feeds", [])

        for f in feeds:
            feed_id = f.get("id", str(uuid.uuid4())[:8])
            url = f.get("url")
            name = f.get("name", "Unknown")
            feed_type = f.get("feed_type", "Unknown")

            if not url:
                continue

            success = storage.add_feed(feed_id, url, name, feed_type)
            if success:
                log.info("Migrated feed: %s (%s)", name, feed_id)
            else:
                log.warning("Failed to migrate feed: %s", name)

        # Keep the JSON file for reference, but it won't be used anymore
        log.info("Feeds migrated from %s to SQLite", _FEEDS_JSON)

    except Exception as e:
        log.error("Failed to migrate feeds from JSON: %s", e)


def _ensure_default_feeds() -> None:
    """Create default feeds if none exist in the database."""
    existing = storage.load_feeds(active_only=False)
    if existing:
        return

    log.info("No feeds found, creating defaults...")

    defaults = [
        ("cnbc", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC Top News", _DEFAULT_FEED_TYPE),
        ("marketwatch", "https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch", _DEFAULT_FEED_TYPE),
        ("bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "Bloomberg Markets", _DEFAULT_FEED_TYPE),
    ]

    for feed_id, url, name, feed_type in defaults:
        success = storage.add_feed(feed_id, url, name, feed_type)
        if success:
            log.info("Created default feed: %s", name)


def load_feeds() -> list[dict]:
    """Load all active feeds from the database."""
    _migrate_feeds_from_json()
    _ensure_default_feeds()
    return storage.load_feeds(active_only=True)


def get_all_feeds() -> list[dict]:
    """Load all feeds (including inactive) from the database."""
    _migrate_feeds_from_json()
    _ensure_default_feeds()
    return storage.load_feeds(active_only=False)


def add_feed(url: str, name: str, feed_type: str) -> dict:
    """Add a new feed to the database.

    Returns the added feed dict with id.
    Raises ValueError if feed URL already exists.
    """
    _migrate_feeds_from_json()

    # Check for duplicate URLs
    existing = storage.load_feeds(active_only=False)
    existing_urls = {f["url"] for f in existing}
    if url in existing_urls:
        raise ValueError("Feed URL already exists")

    feed_id = str(uuid.uuid4())[:8]
    success = storage.add_feed(feed_id, url, name, feed_type)

    if not success:
        raise ValueError("Feed URL already exists")

    new_feed = {
        "id": feed_id,
        "url": url,
        "name": name,
        "feed_type": feed_type,
        "active": True,
        "added_at": "",
    }
    log.info("Added feed: %s (%s)", name, feed_id)
    return new_feed


def delete_feed(feed_id: str) -> bool:
    """Remove a feed by ID."""
    _migrate_feeds_from_json()
    success = storage.delete_feed(feed_id)
    if success:
        log.info("Deleted feed: %s", feed_id)
    return success


def toggle_feed(feed_id: str, active: bool) -> Optional[dict]:
    """Enable/disable a feed."""
    _migrate_feeds_from_json()
    feed = storage.toggle_feed(feed_id, active)
    if feed:
        log.info("Set feed %s active=%s", feed_id, active)
    return feed


def get_feed_urls() -> list[str]:
    """Get list of active feed URLs for use by monitor.py."""
    return [f["url"] for f in load_feeds()]
