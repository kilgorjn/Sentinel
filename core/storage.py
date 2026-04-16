"""
Persist classified news events to MySQL and a Splunk-ready JSON log file.

MySQL stores the full record for analysis and concurrent access:
  SELECT classification, COUNT(*) FROM news_events GROUP BY classification;

The JSON log (one record per line) can be shipped to Splunk with a universal
forwarder pointed at financial_news.log, sourcetype=financial_news.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from . import config
from .db import get_session, RawArticle, NewsEvent, Feed, Meta, MarketSnapshot, init_db

log = logging.getLogger(__name__)


def _title_hash(title: str) -> str:
    """SHA256 of a fully-normalized title — used as the dedup key in raw_articles.

    Falls back to hashing the lowercased original if normalization produces an
    empty string (e.g. titles that are entirely non-ASCII or punctuation), so
    distinct titles always produce distinct hashes.
    """
    normalized = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
    return hashlib.sha256((normalized or title.lower()).encode()).hexdigest()


def initialize():
    """Initialize database tables."""
    init_db()


def save_event(article: dict, result: dict) -> bool:
    """Write a classified article to MySQL and the JSON log file.

    Returns True if the MySQL write succeeded, False on failure.
    The JSON log write is best-effort and does not affect the return value.
    """
    now = datetime.now(timezone.utc)
    pub = article.get("published_at")
    pub_dt = pub if isinstance(pub, datetime) else datetime.fromisoformat(str(pub)) if pub else now

    session = get_session()
    db_ok = False
    try:
        # --- MySQL ---
        event = NewsEvent(
            title=article.get("title", "")[:500],
            source=article.get("source", "")[:100],
            url=article.get("url", "")[:1000],
            published_at=pub_dt,
            classification=result.get("classification", "LOW"),
            confidence=result.get("confidence", 0.0),
            reason=result.get("reason", "")[:500],
            sentiment=result.get("sentiment"),
            created_at=now,
        )
        session.add(event)
        session.commit()
        db_ok = True
    except Exception as e:
        log.error("MySQL write failed: %s", e)
        session.rollback()
    finally:
        session.close()

    # --- JSON log (Splunk-ready) ---
    log_entry = {
        "timestamp": pub_dt.isoformat(),
        "monitored_at": now.isoformat(),
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

    return db_ok


def get_meta(key: str) -> Optional[str]:
    """Return a value from the meta table, or None if not set."""
    session = get_session()
    try:
        row = session.query(Meta).filter(Meta.key == key).first()
        return row.value if row else None
    except Exception:
        return None
    finally:
        session.close()


def set_meta(key: str, value: str) -> None:
    """Upsert a value into the meta table."""
    session = get_session()
    try:
        row = session.query(Meta).filter(Meta.key == key).first()
        if row:
            row.value = value
        else:
            row = Meta(key=key, value=value)
            session.add(row)
        session.commit()
    except Exception as e:
        log.error("Meta write failed: %s", e)
        session.rollback()
    finally:
        session.close()


def already_seen(title: str) -> bool:
    """Return True if this title was stored in the last 24 hours (avoid re-alerting)."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        row = session.query(NewsEvent).filter(
            NewsEvent.title == title,
            NewsEvent.created_at >= cutoff,
        ).first()
        return row is not None
    except Exception:
        return False
    finally:
        session.close()


def summary() -> list[dict]:
    """Return classification counts for console reporting."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = session.query(
            NewsEvent.classification,
            func.count(NewsEvent.id).label("cnt"),
        ).filter(
            NewsEvent.created_at >= cutoff
        ).group_by(NewsEvent.classification).all()

        return [{"classification": r[0], "count": r[1]} for r in rows]
    except Exception as e:
        log.error("Summary query failed: %s", e)
        return []
    finally:
        session.close()


def load_feeds(active_only: bool = True) -> list[dict]:
    """Load feeds from database. If active_only=True, return only active feeds."""
    session = get_session()
    try:
        query = session.query(Feed)
        if active_only:
            query = query.filter(Feed.active.is_(True))
        rows = query.all()
        return [r.to_dict() for r in rows]
    except Exception as e:
        log.error("Failed to load feeds: %s", e)
        return []
    finally:
        session.close()


def add_feed(feed_id: str, url: str, name: str, feed_type: str) -> bool:
    """Add a new feed to the database. Returns True on success, False on duplicate URL."""
    session = get_session()
    try:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        feed = Feed(id=feed_id, url=url, url_hash=url_hash, name=name, feed_type=feed_type)
        session.add(feed)
        session.commit()
        return True
    except IntegrityError:
        log.warning("Duplicate feed URL: %s", url)
        session.rollback()
        return False
    except Exception as e:
        log.error("Unexpected error adding feed %s: %s", url, e)
        session.rollback()
        raise
    finally:
        session.close()


def delete_feed(feed_id: str) -> bool:
    """Delete a feed by ID. Returns True if deleted, False if not found."""
    session = get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if feed:
            session.delete(feed)
            session.commit()
            return True
        return False
    except Exception as e:
        log.error("Failed to delete feed: %s", e)
        session.rollback()
        return False
    finally:
        session.close()


def toggle_feed(feed_id: str, active: bool) -> dict | None:
    """Toggle a feed's active status. Returns the updated feed dict or None if not found."""
    session = get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if feed:
            feed.active = active
            session.commit()
            return feed.to_dict()
        return None
    except Exception as e:
        log.error("Failed to toggle feed: %s", e)
        session.rollback()
        return None
    finally:
        session.close()


def save_snapshots(snapshots: list[dict]) -> None:
    """Bulk insert market data snapshots."""
    if not snapshots:
        return
    session = get_session()
    try:
        rows = [
            {
                "symbol": s["symbol"],
                "name": s.get("name"),
                "region": s.get("region"),
                "price": s.get("price"),
                "prev_close": s.get("prev_close"),
                "change_pct": s.get("change_pct"),
                "high": s.get("high"),
                "low": s.get("low"),
                "fetched_at": datetime.fromisoformat(s["fetched_at"]),
            }
            for s in snapshots
        ]
        session.bulk_insert_mappings(MarketSnapshot, rows)
        session.commit()
    except Exception as e:
        log.error("Market snapshot write failed: %s", e)
        session.rollback()
    finally:
        session.close()


def get_latest_market_data() -> list[dict]:
    """Return the most recent snapshot per symbol."""
    session = get_session()
    try:
        # Subquery to get max fetched_at per symbol
        max_fetched = session.query(
            MarketSnapshot.symbol,
            func.max(MarketSnapshot.fetched_at).label("max_fetched"),
        ).group_by(MarketSnapshot.symbol).subquery()

        rows = session.query(MarketSnapshot).join(
            max_fetched,
            (MarketSnapshot.symbol == max_fetched.c.symbol) &
            (MarketSnapshot.fetched_at == max_fetched.c.max_fetched),
        ).order_by(MarketSnapshot.region, MarketSnapshot.name).all()

        return [r.to_dict() for r in rows]
    except Exception as e:
        log.error("Latest market data query failed: %s", e)
        return []
    finally:
        session.close()


def get_market_history(symbol: str, hours: int = 24) -> list[dict]:
    """Return snapshots for a symbol over the last N hours (for charting)."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = session.query(MarketSnapshot).filter(
            MarketSnapshot.symbol == symbol,
            MarketSnapshot.fetched_at >= cutoff,
        ).order_by(MarketSnapshot.fetched_at).all()

        return [r.to_dict() for r in rows]
    except Exception as e:
        log.error("Market history query failed: %s", e)
        return []
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Raw article pipeline
# ---------------------------------------------------------------------------

def save_raw_articles(articles: list[dict]) -> int:
    """Insert raw fetched articles, skipping duplicates. Returns count inserted.

    Uses MySQL INSERT IGNORE so duplicate title_hash rows are silently skipped
    without rolling back successfully inserted rows in the same batch.
    """
    if not articles:
        return 0
    now = datetime.now(timezone.utc)
    rows = []
    for article in articles:
        title = article.get("title", "").strip()
        if not title:
            continue
        pub = article.get("published_at")
        pub_dt = pub if isinstance(pub, datetime) else (
            datetime.fromisoformat(str(pub)) if pub else now
        )
        rows.append({
            "title_hash": _title_hash(title),
            "title": title,
            "source": article.get("source", ""),
            "url": article.get("url", ""),
            "summary": article.get("summary", ""),
            "published_at": pub_dt,
            "fetched_at": now,
        })
    if not rows:
        return 0
    session = get_session()
    try:
        stmt = mysql_insert(RawArticle).prefix_with("IGNORE").values(rows)
        result = session.execute(stmt)
        session.commit()
        return result.rowcount
    except Exception as e:
        log.error("Raw article batch write failed: %s", e)
        session.rollback()
        return 0
    finally:
        session.close()


CURSOR_KEY = "monitor_last_processed_id"


def get_unclassified_articles(batch_size: int = 50) -> list[dict]:
    """Return up to batch_size raw articles not yet processed by the monitor.

    Uses an ID-based cursor stored in meta.monitor_last_processed_id. Ordering
    by id (auto-increment) is unambiguous — no timestamp collision issues.
    """
    cursor_str = get_meta(CURSOR_KEY)
    last_id = 0
    if cursor_str:
        try:
            last_id = int(cursor_str)
        except (ValueError, TypeError):
            log.warning("Invalid cursor value '%s' — resetting to 0", cursor_str)
            set_meta(CURSOR_KEY, "0")

    session = get_session()
    try:
        rows = session.query(RawArticle).filter(
            RawArticle.id > last_id
        ).order_by(RawArticle.id).limit(batch_size).all()
        return [r.to_dict() for r in rows]
    except Exception as e:
        log.error("Unclassified articles query failed: %s", e)
        return []
    finally:
        session.close()


def advance_cursor(article_id: int) -> None:
    """Advance the classification cursor to the id of the last processed article."""
    set_meta(CURSOR_KEY, str(article_id))
