"""Tests for core/migrations.py — _safe_dt() and migrate_from_sqlite()."""

import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from core.migrations import _safe_dt, migrate_from_sqlite
from core import storage


def _create_sqlite_db(path: str) -> None:
    """Create a minimal SQLite source database with one row per table."""
    conn = sqlite3.connect(path)
    now = "2026-04-15T10:00:00"
    conn.executescript(f"""
        CREATE TABLE news_events (
            id INTEGER PRIMARY KEY, title TEXT, source TEXT, url TEXT,
            published_at TEXT, classification TEXT, confidence REAL,
            reason TEXT, sentiment TEXT, actual_impact TEXT, created_at TEXT
        );
        INSERT INTO news_events VALUES (1,'Fed Cuts','Reuters','https://ex.com',
            '{now}','HIGH',0.9,'Big cut','NEGATIVE',NULL,'{now}');

        CREATE TABLE feeds (
            id TEXT PRIMARY KEY, url TEXT, name TEXT, feed_type TEXT,
            active INTEGER, added_at TEXT
        );
        INSERT INTO feeds VALUES ('f1','https://feed.example.com/rss',
            'Example Feed','RSS 2.0',1,'{now}');

        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('some_key','some_value');

        CREATE TABLE market_snapshots (
            id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, region TEXT,
            price REAL, prev_close REAL, change_pct REAL,
            high REAL, low REAL, fetched_at TEXT
        );
        INSERT INTO market_snapshots VALUES (1,'SPX','S&P 500','us',
            5000.0,4950.0,1.01,5010.0,4940.0,'{now}');
    """)
    conn.commit()
    conn.close()


class TestSafeDt:
    def test_parses_iso_string(self):
        result = _safe_dt("2026-04-15T10:30:00")
        assert result == datetime(2026, 4, 15, 10, 30, 0)

    def test_returns_none_for_none(self):
        assert _safe_dt(None) is None

    def test_returns_none_for_empty_string(self):
        assert _safe_dt("") is None

    def test_returns_fallback_on_invalid_string(self):
        fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _safe_dt("not-a-date", fallback=fallback)
        assert result == fallback

    def test_returns_none_on_invalid_without_fallback(self):
        assert _safe_dt("not-a-date") is None

    def test_returns_none_for_zero(self):
        assert _safe_dt(0) is None


class TestMigrateFromSqlite:
    def test_skips_when_no_env_var(self):
        with patch.dict(os.environ, {"SENTINEL_DB_PATH": "", "SQLITE_DB_PATH": ""}):
            result = migrate_from_sqlite()
        assert result is True

    def test_skips_when_file_missing(self):
        with patch.dict(os.environ, {"SENTINEL_DB_PATH": "/tmp/nonexistent_sentinel_test.db"}):
            result = migrate_from_sqlite()
        assert result is True

    def test_skips_when_already_completed(self):
        storage.set_meta("sqlite_migration_completed", "2026-04-15T10:00:00")
        result = migrate_from_sqlite()
        assert result is True

    def test_migrates_news_events(self):
        from core.db import get_session, NewsEvent
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_sqlite_db(db_path)
            with patch.dict(os.environ, {"SENTINEL_DB_PATH": db_path, "SQLITE_DB_PATH": ""}):
                result = migrate_from_sqlite()
            assert result is True
            session = get_session()
            try:
                events = session.query(NewsEvent).all()
                assert len(events) == 1
                assert events[0].title == "Fed Cuts"
                assert events[0].classification == "HIGH"
            finally:
                session.close()
        finally:
            os.unlink(db_path)

    def test_migrates_feeds(self):
        from core.db import get_session, Feed
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_sqlite_db(db_path)
            with patch.dict(os.environ, {"SENTINEL_DB_PATH": db_path, "SQLITE_DB_PATH": ""}):
                migrate_from_sqlite()
            session = get_session()
            try:
                feeds = session.query(Feed).all()
                assert len(feeds) == 1
                assert feeds[0].url == "https://feed.example.com/rss"
            finally:
                session.close()
        finally:
            os.unlink(db_path)

    def test_migrates_meta(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_sqlite_db(db_path)
            with patch.dict(os.environ, {"SENTINEL_DB_PATH": db_path, "SQLITE_DB_PATH": ""}):
                migrate_from_sqlite()
            assert storage.get_meta("some_key") == "some_value"
        finally:
            os.unlink(db_path)

    def test_sets_completion_flag(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_sqlite_db(db_path)
            with patch.dict(os.environ, {"SENTINEL_DB_PATH": db_path, "SQLITE_DB_PATH": ""}):
                migrate_from_sqlite()
            assert storage.get_meta("sqlite_migration_completed") is not None
        finally:
            os.unlink(db_path)

    def test_idempotent_second_run(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _create_sqlite_db(db_path)
            with patch.dict(os.environ, {"SENTINEL_DB_PATH": db_path, "SQLITE_DB_PATH": ""}):
                assert migrate_from_sqlite() is True
                assert migrate_from_sqlite() is True
        finally:
            os.unlink(db_path)
