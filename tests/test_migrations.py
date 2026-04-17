"""Tests for core/migrations.py — helper functions and skip logic."""

import sqlite3
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base, NewsEvent, Feed, Meta, MarketSnapshot
from core.migrations import (
    _sqlite_path_to_migrate,
    _migrate_news_events,
    _migrate_feeds,
    _migrate_meta,
    _migrate_market_snapshots,
    MIGRATION_FLAG,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session():
    """Return a fresh in-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _source_conn(schema_sql: str, rows: list[tuple], table: str) -> sqlite3.Connection:
    """Create a temporary SQLite source DB with one table and given rows."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(schema_sql)
    conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows) if rows else None
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# _sqlite_path_to_migrate
# ---------------------------------------------------------------------------

class TestSqlitePathToMigrate:
    def test_returns_none_when_flag_set(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = MagicMock()
        with patch("core.migrations.get_session", return_value=mock_session):
            result = _sqlite_path_to_migrate()
        assert result is None

    def test_returns_none_when_env_not_set(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("core.migrations.get_session", return_value=mock_session), \
             patch.dict("os.environ", {}, clear=True):
            result = _sqlite_path_to_migrate()
        assert result is None

    def test_returns_none_when_file_missing(self, tmp_path):
        missing = str(tmp_path / "nonexistent.db")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("core.migrations.get_session", return_value=mock_session), \
             patch.dict("os.environ", {"SENTINEL_DB_PATH": missing}):
            result = _sqlite_path_to_migrate()
        assert result is None

    def test_returns_path_when_file_exists(self, tmp_path):
        db_file = tmp_path / "news_events.db"
        db_file.touch()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("core.migrations.get_session", return_value=mock_session), \
             patch.dict("os.environ", {"SENTINEL_DB_PATH": str(db_file)}):
            result = _sqlite_path_to_migrate()
        assert result == db_file

    def test_uses_sqlite_db_path_fallback(self, tmp_path):
        db_file = tmp_path / "fallback.db"
        db_file.touch()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with patch("core.migrations.get_session", return_value=mock_session), \
             patch.dict("os.environ", {"SQLITE_DB_PATH": str(db_file)}):
            result = _sqlite_path_to_migrate()
        assert result == db_file


# ---------------------------------------------------------------------------
# _migrate_news_events
# ---------------------------------------------------------------------------

_NEWS_SCHEMA = """
CREATE TABLE news_events (
    id INTEGER PRIMARY KEY,
    title TEXT,
    source TEXT,
    url TEXT,
    published_at TEXT,
    classification TEXT,
    confidence REAL,
    reason TEXT,
    sentiment TEXT,
    actual_impact TEXT,
    created_at TEXT
)
"""
_NOW_ISO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()


class TestMigrateNewsEvents:
    def test_queues_valid_row(self):
        session = _make_session()
        row = (1, "Fed cuts rates", "Reuters", "https://x.com", _NOW_ISO,
               "HIGH", 0.9, "Big news", "NEGATIVE", None, _NOW_ISO)
        conn = _source_conn(_NEWS_SCHEMA, [row], "news_events")
        now = datetime.now(timezone.utc)

        _migrate_news_events(session, conn, now)
        session.commit()

        assert session.query(NewsEvent).count() == 1
        event = session.query(NewsEvent).first()
        assert event.title == "Fed cuts rates"
        assert event.classification == "HIGH"

    def test_uses_fallback_for_bad_timestamp(self):
        # _safe_dt is called with fallback=now so bad timestamps never cause a skip;
        # the row is queued using now as the fallback value.
        session = _make_session()
        now = datetime.now(timezone.utc)
        row = (2, "Bad ts", "Reuters", "https://x.com", "NOT-A-DATE",
               "LOW", 0.5, "reason", "NEUTRAL", None, "ALSO-BAD")
        conn = _source_conn(_NEWS_SCHEMA, [row], "news_events")

        _migrate_news_events(session, conn, now)
        session.commit()

        assert session.query(NewsEvent).count() == 1

    def test_queues_multiple_rows(self):
        session = _make_session()
        rows = [
            (i, f"Title {i}", "Reuters", f"https://x.com/{i}", _NOW_ISO,
             "LOW", 0.5, "reason", "NEUTRAL", None, _NOW_ISO)
            for i in range(1, 4)
        ]
        conn = _source_conn(_NEWS_SCHEMA, rows, "news_events")
        now = datetime.now(timezone.utc)

        _migrate_news_events(session, conn, now)
        session.commit()

        assert session.query(NewsEvent).count() == 3

    def test_empty_source_table(self):
        session = _make_session()
        conn = _source_conn(_NEWS_SCHEMA, [], "news_events")
        now = datetime.now(timezone.utc)

        _migrate_news_events(session, conn, now)
        session.commit()

        assert session.query(NewsEvent).count() == 0


# ---------------------------------------------------------------------------
# _migrate_feeds
# ---------------------------------------------------------------------------

_FEED_SCHEMA = """
CREATE TABLE feeds (
    id TEXT PRIMARY KEY,
    url TEXT,
    name TEXT,
    feed_type TEXT,
    active INTEGER,
    added_at TEXT
)
"""


class TestMigrateFeeds:
    def test_queues_valid_feed(self):
        session = _make_session()
        row = ("abc123", "https://feeds.example.com/rss", "Example", "RSS 2.0", 1, _NOW_ISO)
        conn = _source_conn(_FEED_SCHEMA, [row], "feeds")
        now = datetime.now(timezone.utc)

        _migrate_feeds(session, conn, now)
        session.commit()

        assert session.query(Feed).count() == 1
        feed = session.query(Feed).first()
        assert feed.name == "Example"
        assert feed.active is True

    def test_url_hash_populated(self):
        import hashlib
        session = _make_session()
        url = "https://feeds.example.com/rss"
        row = ("abc123", url, "Example", "RSS 2.0", 1, _NOW_ISO)
        conn = _source_conn(_FEED_SCHEMA, [row], "feeds")

        _migrate_feeds(session, conn, datetime.now(timezone.utc))
        session.commit()

        feed = session.query(Feed).first()
        assert feed.url_hash == hashlib.sha256(url.encode()).hexdigest()

    def test_empty_source_table(self):
        session = _make_session()
        conn = _source_conn(_FEED_SCHEMA, [], "feeds")

        _migrate_feeds(session, conn, datetime.now(timezone.utc))
        session.commit()

        assert session.query(Feed).count() == 0


# ---------------------------------------------------------------------------
# _migrate_meta
# ---------------------------------------------------------------------------

_META_SCHEMA = "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)"


class TestMigrateMeta:
    def test_queues_key_value(self):
        session = _make_session()
        conn = _source_conn(_META_SCHEMA, [("cursor", "42")], "meta")

        _migrate_meta(session, conn)
        session.commit()

        row = session.query(Meta).filter(Meta.key == "cursor").first()
        assert row is not None
        assert row.value == "42"

    def test_skips_migration_flag(self):
        session = _make_session()
        conn = _source_conn(_META_SCHEMA, [(MIGRATION_FLAG, "done"), ("other", "val")], "meta")

        _migrate_meta(session, conn)
        session.commit()

        assert session.query(Meta).filter(Meta.key == MIGRATION_FLAG).first() is None
        assert session.query(Meta).filter(Meta.key == "other").first() is not None

    def test_skips_already_present_key(self):
        session = _make_session()
        session.add(Meta(key="existing", value="old"))
        session.commit()

        conn = _source_conn(_META_SCHEMA, [("existing", "new")], "meta")
        _migrate_meta(session, conn)
        session.commit()

        row = session.query(Meta).filter(Meta.key == "existing").first()
        assert row.value == "old"  # not overwritten

    def test_empty_source_table(self):
        session = _make_session()
        conn = _source_conn(_META_SCHEMA, [], "meta")

        _migrate_meta(session, conn)
        session.commit()

        assert session.query(Meta).count() == 0


# ---------------------------------------------------------------------------
# _migrate_market_snapshots
# ---------------------------------------------------------------------------

_SNAPSHOT_SCHEMA = """
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    region TEXT,
    price REAL,
    prev_close REAL,
    change_pct REAL,
    high REAL,
    low REAL,
    fetched_at TEXT
)
"""


class TestMigrateMarketSnapshots:
    def test_queues_valid_snapshot(self):
        session = _make_session()
        row = (1, "SPX", "S&P 500", "US", 5000.0, 4950.0, 1.01, 5010.0, 4940.0, _NOW_ISO)
        conn = _source_conn(_SNAPSHOT_SCHEMA, [row], "market_snapshots")

        _migrate_market_snapshots(session, conn)
        session.commit()

        assert session.query(MarketSnapshot).count() == 1
        snap = session.query(MarketSnapshot).first()
        assert snap.symbol == "SPX"
        assert snap.price == pytest.approx(5000.0)

    def test_skips_row_with_bad_fetched_at(self):
        session = _make_session()
        row = (2, "DJI", "Dow Jones", "US", 40000.0, 39000.0, 2.56, 40100.0, 39900.0, "BAD-DATE")
        conn = _source_conn(_SNAPSHOT_SCHEMA, [row], "market_snapshots")

        _migrate_market_snapshots(session, conn)
        session.commit()

        assert session.query(MarketSnapshot).count() == 0

    def test_empty_source_table(self):
        session = _make_session()
        conn = _source_conn(_SNAPSHOT_SCHEMA, [], "market_snapshots")

        _migrate_market_snapshots(session, conn)
        session.commit()

        assert session.query(MarketSnapshot).count() == 0
