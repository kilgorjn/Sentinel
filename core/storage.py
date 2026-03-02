"""
Persist classified news events to SQLite and a Splunk-ready JSON log file.

SQLite stores the full record for later accuracy analysis:
  SELECT classification, COUNT(*) FROM news_events GROUP BY classification;

The JSON log (one record per line) can be shipped to Splunk with a universal
forwarder pointed at financial_news.log, sourcetype=financial_news.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from . import config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    source          TEXT,
    url             TEXT,
    published_at    TEXT,
    classification  TEXT NOT NULL,
    confidence      REAL,
    reason          TEXT,
    sentiment       TEXT,
    actual_impact   TEXT,        -- filled in manually after Splunk correlation
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classification ON news_events(classification);
CREATE INDEX IF NOT EXISTS idx_created_at     ON news_events(created_at);

CREATE TABLE IF NOT EXISTS feeds (
    id          TEXT PRIMARY KEY,
    url         TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    feed_type   TEXT,
    active      BOOLEAN DEFAULT 1,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Keep one connection open for the process lifetime
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.executescript(_SCHEMA)
        # Migrate existing databases that predate the sentiment column
        try:
            _conn.execute("ALTER TABLE news_events ADD COLUMN sentiment TEXT")
            _conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
    return _conn


def save_event(article: dict, result: dict) -> None:
    """Write a classified article to SQLite and the JSON log file."""
    now = datetime.now(timezone.utc).isoformat()
    pub = article.get("published_at")
    pub_str = pub.isoformat() if isinstance(pub, datetime) else str(pub or now)

    # --- SQLite ---
    try:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO news_events
              (title, source, url, published_at, classification, confidence, reason, sentiment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.get("title", ""),
                article.get("source", ""),
                article.get("url", ""),
                pub_str,
                result.get("classification", "LOW"),
                result.get("confidence", 0.0),
                result.get("reason", ""),
                result.get("sentiment"),
                now,
            ),
        )
        conn.commit()
    except Exception as e:
        log.error("SQLite write failed: %s", e)

    # --- JSON log (Splunk-ready) ---
    log_entry = {
        "timestamp": pub_str,
        "monitored_at": now,
        "source": article.get("source", ""),
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "classification": result.get("classification", "LOW"),
        "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason", ""),
        "sentiment": result.get("sentiment"),
    }
    try:
        with open(config.LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        log.error("Log file write failed: %s", e)


def get_meta(key: str) -> str | None:
    """Return a value from the meta table, or None if not set."""
    try:
        row = _get_conn().execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def set_meta(key: str, value: str) -> None:
    """Upsert a value into the meta table."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()
    except Exception as e:
        log.error("Meta write failed: %s", e)


def already_seen(title: str) -> bool:
    """Return True if this title was stored in the last 24 hours (avoid re-alerting)."""
    try:
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT 1 FROM news_events
            WHERE title = ?
              AND created_at >= datetime('now', '-24 hours')
            LIMIT 1
            """,
            (title,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def summary() -> list[dict]:
    """Return classification counts for console reporting."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT classification, COUNT(*) as cnt
            FROM news_events
            WHERE created_at >= datetime('now', '-24 hours')
            GROUP BY classification
            ORDER BY cnt DESC
            """
        ).fetchall()
        return [{"classification": r[0], "count": r[1]} for r in rows]
    except Exception as e:
        log.error("Summary query failed: %s", e)
        return []


def load_feeds(active_only: bool = True) -> list[dict]:
    """Load feeds from database. If active_only=True, return only active feeds."""
    try:
        conn = _get_conn()
        if active_only:
            rows = conn.execute("SELECT id, url, name, feed_type, active, added_at FROM feeds WHERE active = 1").fetchall()
        else:
            rows = conn.execute("SELECT id, url, name, feed_type, active, added_at FROM feeds").fetchall()
        return [
            {
                "id": r[0],
                "url": r[1],
                "name": r[2],
                "feed_type": r[3],
                "active": bool(r[4]),
                "added_at": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        log.error("Failed to load feeds: %s", e)
        return []


def add_feed(feed_id: str, url: str, name: str, feed_type: str) -> bool:
    """Add a new feed to the database. Returns True on success, False on error (e.g., duplicate URL)."""
    try:
        conn = _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO feeds (id, url, name, feed_type, active, added_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (feed_id, url, name, feed_type, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate URL
        log.warning("Duplicate feed URL: %s", url)
        return False
    except Exception as e:
        log.error("Failed to add feed: %s", e)
        return False


def delete_feed(feed_id: str) -> bool:
    """Delete a feed by ID. Returns True if deleted, False if not found."""
    try:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        log.error("Failed to delete feed: %s", e)
        return False


def toggle_feed(feed_id: str, active: bool) -> dict | None:
    """Toggle a feed's active status. Returns the updated feed dict or None if not found."""
    try:
        conn = _get_conn()
        conn.execute("UPDATE feeds SET active = ? WHERE id = ?", (active, feed_id))
        conn.commit()

        # Fetch and return the updated feed
        row = conn.execute("SELECT id, url, name, feed_type, active, added_at FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        if row:
            return {
                "id": row[0],
                "url": row[1],
                "name": row[2],
                "feed_type": row[3],
                "active": bool(row[4]),
                "added_at": row[5],
            }
        return None
    except Exception as e:
        log.error("Failed to toggle feed: %s", e)
        return None
