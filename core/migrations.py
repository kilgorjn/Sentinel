"""Data migration from SQLite to MySQL.

On first MySQL setup, this script automatically migrates data from the
existing SQLite database (if present) to MySQL.
"""

import sqlite3
import logging
import hashlib
from datetime import datetime
from pathlib import Path

from . import config
from .db import get_session, NewsEvent, Feed, Meta, MarketSnapshot

log = logging.getLogger(__name__)


def migrate_from_sqlite() -> bool:
    """Migrate data from SQLite to MySQL if SQLite database exists.

    Returns True if migration completed (or skipped because no SQLite DB),
    False if migration failed.
    """
    sqlite_path = Path(config.DB_PATH)

    # Check if SQLite database exists
    if not sqlite_path.exists():
        log.info("No SQLite database found at %s — skipping migration", sqlite_path)
        return True

    log.info("Found SQLite database at %s — migrating to MySQL", sqlite_path)

    session = get_session()
    try:
        # Open SQLite connection
        sqlite_conn = sqlite3.connect(str(sqlite_path))
        sqlite_conn.row_factory = sqlite3.Row

        # Migrate news_events
        log.info("Migrating news_events...")
        cursor = sqlite_conn.execute("SELECT * FROM news_events")
        rows = cursor.fetchall()
        migrated = 0
        for row in rows:
            try:
                event = NewsEvent(
                    id=row["id"],
                    title=row["title"],
                    source=row["source"],
                    url=row["url"],
                    published_at=datetime.fromisoformat(row["published_at"]),
                    classification=row["classification"],
                    confidence=row["confidence"],
                    reason=row["reason"],
                    sentiment=row["sentiment"],
                    actual_impact=row.get("actual_impact"),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                session.add(event)
                migrated += 1
            except Exception as e:
                log.warning("Failed to migrate event row: %s", e)
        session.commit()
        log.info("Migrated %d news_events", migrated)

        # Migrate feeds
        log.info("Migrating feeds...")
        cursor = sqlite_conn.execute("SELECT * FROM feeds")
        rows = cursor.fetchall()
        migrated = 0
        for row in rows:
            try:
                url = row["url"]
                feed = Feed(
                    id=row["id"],
                    url=url,
                    url_hash=hashlib.sha256(url.encode()).hexdigest(),
                    name=row["name"],
                    feed_type=row.get("feed_type"),
                    active=bool(row["active"]),
                    added_at=datetime.fromisoformat(row["added_at"]),
                )
                session.add(feed)
                migrated += 1
            except Exception as e:
                log.warning("Failed to migrate feed row: %s", e)
        session.commit()
        log.info("Migrated %d feeds", migrated)

        # Migrate meta
        log.info("Migrating meta...")
        cursor = sqlite_conn.execute("SELECT * FROM meta")
        rows = cursor.fetchall()
        migrated = 0
        for row in rows:
            try:
                meta = Meta(key=row["key"], value=row["value"])
                session.add(meta)
                migrated += 1
            except Exception as e:
                log.warning("Failed to migrate meta row: %s", e)
        session.commit()
        log.info("Migrated %d meta entries", migrated)

        # Migrate market_snapshots
        log.info("Migrating market_snapshots...")
        cursor = sqlite_conn.execute("SELECT * FROM market_snapshots")
        rows = cursor.fetchall()
        migrated = 0
        for row in rows:
            try:
                snapshot = MarketSnapshot(
                    id=row["id"],
                    symbol=row["symbol"],
                    name=row.get("name"),
                    region=row.get("region"),
                    price=row.get("price"),
                    prev_close=row.get("prev_close"),
                    change_pct=row.get("change_pct"),
                    high=row.get("high"),
                    low=row.get("low"),
                    fetched_at=datetime.fromisoformat(row["fetched_at"]),
                )
                session.add(snapshot)
                migrated += 1
            except Exception as e:
                log.warning("Failed to migrate snapshot row: %s", e)
        session.commit()
        log.info("Migrated %d market_snapshots", migrated)

        sqlite_conn.close()
        log.info("Migration completed successfully")
        return True

    except Exception as e:
        log.error("Migration failed: %s", e, exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()
