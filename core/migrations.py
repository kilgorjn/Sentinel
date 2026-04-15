"""Data migration from SQLite to MySQL.

On first MySQL setup, this script automatically migrates data from the
existing SQLite database (if present) to MySQL.

Idempotent: a 'sqlite_migration_completed' meta key is set on success,
preventing re-migration on subsequent restarts.
"""

import os
import sqlite3
import logging
import hashlib
from datetime import datetime
from pathlib import Path

from .db import get_session, NewsEvent, Feed, Meta, MarketSnapshot

log = logging.getLogger(__name__)

MIGRATION_FLAG = "sqlite_migration_completed"


def migrate_from_sqlite() -> bool:
    """Migrate data from SQLite to MySQL if SQLite database exists.

    Idempotent — checks for a completion flag in the meta table before
    running. Safe to call on every startup.

    Returns True if migration completed or was already done, False on failure.
    """
    # Check idempotency flag first
    session = get_session()
    try:
        flag = session.query(Meta).filter(Meta.key == MIGRATION_FLAG).first()
        if flag:
            log.info("SQLite migration already completed — skipping")
            return True
    finally:
        session.close()

    # Determine SQLite path — prefer explicit env var, fall back to config
    sqlite_db_path = os.getenv("SENTINEL_DB_PATH") or os.getenv("SQLITE_DB_PATH")
    if not sqlite_db_path:
        log.info("SENTINEL_DB_PATH not set — skipping SQLite migration")
        return True

    sqlite_path = Path(sqlite_db_path)
    if not sqlite_path.exists():
        log.info("No SQLite database found at %s — skipping migration", sqlite_path)
        return True

    log.info("Found SQLite database at %s — migrating to MySQL", sqlite_path)

    session = get_session()
    sqlite_conn = None
    try:
        sqlite_conn = sqlite3.connect(str(sqlite_path))
        sqlite_conn.row_factory = sqlite3.Row

        # Migrate news_events
        log.info("Migrating news_events...")
        rows = sqlite_conn.execute("SELECT * FROM news_events").fetchall()
        col_names = [d[0] for d in sqlite_conn.execute("SELECT * FROM news_events LIMIT 0").description]
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
                    actual_impact=row["actual_impact"] if "actual_impact" in col_names else None,
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                session.add(event)
                migrated += 1
            except Exception as e:
                log.warning("Skipping event row (id=%s): %s", row["id"], e)
        session.commit()
        log.info("Migrated %d news_events", migrated)

        # Migrate feeds
        log.info("Migrating feeds...")
        rows = sqlite_conn.execute("SELECT * FROM feeds").fetchall()
        migrated = 0
        for row in rows:
            try:
                url = row["url"]
                feed = Feed(
                    id=row["id"],
                    url=url,
                    url_hash=hashlib.sha256(url.encode()).hexdigest(),
                    name=row["name"],
                    feed_type=row["feed_type"],
                    active=bool(row["active"]),
                    added_at=datetime.fromisoformat(row["added_at"]),
                )
                session.add(feed)
                migrated += 1
            except Exception as e:
                log.warning("Skipping feed row (id=%s): %s", row["id"], e)
        session.commit()
        log.info("Migrated %d feeds", migrated)

        # Migrate meta (skip the migration flag key itself)
        log.info("Migrating meta...")
        rows = sqlite_conn.execute("SELECT * FROM meta").fetchall()
        migrated = 0
        for row in rows:
            try:
                if row["key"] == MIGRATION_FLAG:
                    continue
                session.add(Meta(key=row["key"], value=row["value"]))
                migrated += 1
            except Exception as e:
                log.warning("Skipping meta row (key=%s): %s", row["key"], e)
        session.commit()
        log.info("Migrated %d meta entries", migrated)

        # Migrate market_snapshots
        log.info("Migrating market_snapshots...")
        rows = sqlite_conn.execute("SELECT * FROM market_snapshots").fetchall()
        migrated = 0
        for row in rows:
            try:
                snapshot = MarketSnapshot(
                    id=row["id"],
                    symbol=row["symbol"],
                    name=row["name"],
                    region=row["region"],
                    price=row["price"],
                    prev_close=row["prev_close"],
                    change_pct=row["change_pct"],
                    high=row["high"],
                    low=row["low"],
                    fetched_at=datetime.fromisoformat(row["fetched_at"]),
                )
                session.add(snapshot)
                migrated += 1
            except Exception as e:
                log.warning("Skipping snapshot row (id=%s): %s", row["id"], e)
        session.commit()
        log.info("Migrated %d market_snapshots", migrated)

        # Set idempotency flag
        session.add(Meta(key=MIGRATION_FLAG, value=datetime.utcnow().isoformat()))
        session.commit()

        log.info("SQLite migration completed successfully")
        return True

    except Exception as e:
        log.error("Migration failed: %s", e, exc_info=True)
        session.rollback()
        return False
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        session.close()
