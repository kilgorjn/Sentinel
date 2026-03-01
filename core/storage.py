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
    actual_impact   TEXT,        -- filled in manually after Splunk correlation
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classification ON news_events(classification);
CREATE INDEX IF NOT EXISTS idx_created_at     ON news_events(created_at);
"""

# Keep one connection open for the process lifetime
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.executescript(_SCHEMA)
        _conn.commit()
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
              (title, source, url, published_at, classification, confidence, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.get("title", ""),
                article.get("source", ""),
                article.get("url", ""),
                pub_str,
                result.get("classification", "LOW"),
                result.get("confidence", 0.0),
                result.get("reason", ""),
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
    }
    try:
        with open(config.LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        log.error("Log file write failed: %s", e)


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
