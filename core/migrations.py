"""Data migration from SQLite to MySQL.

On first MySQL setup, this script automatically migrates data from the
existing SQLite database (if present) to MySQL.

Idempotent: a 'sqlite_migration_completed' meta key is set on success,
preventing re-migration on subsequent restarts.

Atomic: all tables are migrated in a single transaction. If anything fails,
nothing is committed and the completion flag is not set, so the next startup
retries cleanly.
"""

import os
import sqlite3
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.exc import IntegrityError

from .db import get_session, NewsEvent, Feed, Meta, MarketSnapshot

log = logging.getLogger(__name__)

MIGRATION_FLAG = "sqlite_migration_completed"


def _safe_dt(value: object, fallback: Optional[datetime] = None) -> Optional[datetime]:
    """Parse an ISO datetime string safely, returning fallback on failure."""
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return fallback


def _migrate_news_events(session, sqlite_conn, now: datetime) -> None:
    """Queue all news_events rows from SQLite into the session."""
    log.info("Migrating news_events...")
    rows = sqlite_conn.execute("SELECT * FROM news_events").fetchall()
    col_names = {d[0] for d in sqlite_conn.execute(
        "SELECT * FROM news_events LIMIT 0"
    ).description}
    migrated = skipped = 0
    for row in rows:
        pub = _safe_dt(row["published_at"], fallback=now)
        created = _safe_dt(row["created_at"], fallback=now)
        if pub is None or created is None:
            log.warning("Skipping event id=%s: unparseable timestamps", row["id"])
            skipped += 1
            continue
        try:
            session.add(NewsEvent(
                id=row["id"],
                title=row["title"],
                source=row["source"],
                url=row["url"],
                published_at=pub,
                classification=row["classification"],
                confidence=row["confidence"],
                reason=row["reason"],
                sentiment=row["sentiment"],
                actual_impact=row["actual_impact"] if "actual_impact" in col_names else None,
                created_at=created,
            ))
            migrated += 1
        except Exception as e:
            log.warning("Skipping event id=%s: %s", row["id"], e)
            skipped += 1
    log.info("Queued %d news_events (%d skipped)", migrated, skipped)


def _migrate_feeds(session, sqlite_conn, now: datetime) -> None:
    """Queue all feeds rows from SQLite into the session."""
    log.info("Migrating feeds...")
    rows = sqlite_conn.execute("SELECT * FROM feeds").fetchall()
    migrated = skipped = 0
    for row in rows:
        added = _safe_dt(row["added_at"], fallback=now)
        try:
            url = row["url"]
            session.add(Feed(
                id=row["id"],
                url=url,
                url_hash=hashlib.sha256(url.encode()).hexdigest(),
                name=row["name"],
                feed_type=row["feed_type"],
                active=bool(row["active"]),
                added_at=added or now,
            ))
            migrated += 1
        except Exception as e:
            log.warning("Skipping feed id=%s: %s", row["id"], e)
            skipped += 1
    log.info("Queued %d feeds (%d skipped)", migrated, skipped)


def _migrate_meta(session, sqlite_conn) -> None:
    """Queue all meta rows from SQLite into the session, skipping existing keys."""
    log.info("Migrating meta...")
    rows = sqlite_conn.execute("SELECT * FROM meta").fetchall()
    existing_meta_keys = {r.key for r in session.query(Meta).all()}
    migrated = skipped = 0
    for row in rows:
        if row["key"] == MIGRATION_FLAG:
            continue
        if row["key"] in existing_meta_keys:
            log.debug("Skipping already-present meta key: %s", row["key"])
            skipped += 1
            continue
        try:
            session.add(Meta(key=row["key"], value=row["value"]))
            migrated += 1
        except Exception as e:
            log.warning("Skipping meta key=%s: %s", row["key"], e)
            skipped += 1
    log.info("Queued %d meta entries (%d skipped)", migrated, skipped)


def _migrate_market_snapshots(session, sqlite_conn) -> None:
    """Queue all market_snapshots rows from SQLite into the session."""
    log.info("Migrating market_snapshots...")
    rows = sqlite_conn.execute("SELECT * FROM market_snapshots").fetchall()
    migrated = skipped = 0
    for row in rows:
        fetched = _safe_dt(row["fetched_at"])
        if not fetched:
            log.warning("Skipping snapshot id=%s: unparseable fetched_at", row["id"])
            skipped += 1
            continue
        try:
            session.add(MarketSnapshot(
                id=row["id"],
                symbol=row["symbol"],
                name=row["name"],
                region=row["region"],
                price=row["price"],
                prev_close=row["prev_close"],
                change_pct=row["change_pct"],
                high=row["high"],
                low=row["low"],
                fetched_at=fetched,
            ))
            migrated += 1
        except Exception as e:
            log.warning("Skipping snapshot id=%s: %s", row["id"], e)
            skipped += 1
    log.info("Queued %d market_snapshots (%d skipped)", migrated, skipped)


def _sqlite_path_to_migrate() -> Optional[Path]:
    """Return the SQLite path to migrate, or None if migration should be skipped."""
    session = get_session()
    try:
        if session.query(Meta).filter(Meta.key == MIGRATION_FLAG).first():
            log.info("SQLite migration already completed — skipping")
            return None
    finally:
        session.close()

    sqlite_db_path = os.getenv("SENTINEL_DB_PATH") or os.getenv("SQLITE_DB_PATH")
    if not sqlite_db_path:
        log.info("SENTINEL_DB_PATH not set — skipping SQLite migration")
        return None

    sqlite_path = Path(sqlite_db_path)
    if not sqlite_path.exists():
        log.info("No SQLite database found at %s — skipping migration", sqlite_path)
        return None

    return sqlite_path


def migrate_from_sqlite() -> bool:
    """Migrate data from SQLite to MySQL if SQLite database exists.

    Idempotent  — checks for a completion flag before running.
    Atomic      — uses a single transaction; nothing commits unless everything
                  succeeds, so a crash mid-migration leaves MySQL clean for retry.

    Returns True if migration completed or was already done, False on failure.
    """
    sqlite_path = _sqlite_path_to_migrate()
    if sqlite_path is None:
        return True

    log.info("Found SQLite database at %s — migrating to MySQL", sqlite_path)

    session = get_session()
    sqlite_conn = None

    try:
        sqlite_conn = sqlite3.connect(str(sqlite_path))
        sqlite_conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc)

        _migrate_news_events(session, sqlite_conn, now)
        _migrate_feeds(session, sqlite_conn, now)
        _migrate_meta(session, sqlite_conn)
        _migrate_market_snapshots(session, sqlite_conn)

        # Set completion flag and commit everything atomically
        session.add(Meta(key=MIGRATION_FLAG, value=now.isoformat()))
        session.commit()

        log.info("SQLite migration completed successfully")
        return True

    except Exception as e:
        log.error("Migration failed — rolling back: %s", e, exc_info=True)
        session.rollback()
        return False
    finally:
        if sqlite_conn:
            sqlite_conn.close()
        session.close()
