"""Fetch and parse financial news from RSS feeds and optionally NewsAPI."""

import re
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from . import config, storage

log = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """Lowercase + strip punctuation for deduplication."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def _parse_time(entry) -> datetime:
    """Extract published datetime from a feedparser entry."""
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def fetch_rss() -> list[dict]:
    """Fetch all configured RSS feeds and return normalized articles."""
    articles = []
    agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    for url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=agent)
            source = getattr(feed, "feed", {}).get("title", url)
            for entry in getattr(feed, "entries", []):
                articles.append({
                    "source": source,
                    "title": entry.get("title", "").strip(),
                    "summary": entry.get("summary", "")[:400],
                    "url": entry.get("link", ""),
                    "published_at": _parse_time(entry),
                })
            log.debug("Fetched %d articles from %s", len(feed.entries), url)
        except Exception as e:
            log.warning("RSS fetch failed for %s: %s", url, e)
    return articles


def _newsapi_rate_ok() -> bool:
    """Return True if we are allowed to call NewsAPI right now."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # Daily cap
    count = int(storage.get_meta(f"newsapi_count_{today}") or "0")
    if count >= config.NEWSAPI_DAILY_LIMIT:
        log.warning("NewsAPI daily limit reached (%d/%d) — skipping until tomorrow",
                    count, config.NEWSAPI_DAILY_LIMIT)
        return False

    # Minimum interval
    last_str = storage.get_meta("newsapi_last_fetch")
    if last_str:
        last = datetime.fromisoformat(last_str)
        elapsed = (now - last).total_seconds()
        if elapsed < config.NEWSAPI_MIN_INTERVAL_SECONDS:
            log.debug("NewsAPI cooldown: %.0fs remaining",
                      config.NEWSAPI_MIN_INTERVAL_SECONDS - elapsed)
            return False

    return True


def _newsapi_record_fetch() -> None:
    """Increment daily counter and update last-fetch timestamp."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    count = int(storage.get_meta(f"newsapi_count_{today}") or "0")
    storage.set_meta(f"newsapi_count_{today}", str(count + 1))
    storage.set_meta("newsapi_last_fetch", now.isoformat())
    log.debug("NewsAPI request #%d today", count + 1)


def fetch_newsapi() -> list[dict]:
    """Fetch from NewsAPI if configured and within rate limits."""
    if not config.NEWSAPI_KEY:
        return []
    if not _newsapi_rate_ok():
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": config.NEWSAPI_QUERY,
                "sortBy": "publishedAt",
                "apiKey": config.NEWSAPI_KEY,
                "pageSize": 30,
                "language": "en",
            },
            timeout=15,
        )
        resp.raise_for_status()
        _newsapi_record_fetch()
        data = resp.json()
        articles = []
        for a in data.get("articles", []):
            pub = a.get("publishedAt", "")
            try:
                published_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                published_at = datetime.now(timezone.utc)
            articles.append({
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "title": (a.get("title") or "").strip(),
                "summary": (a.get("description") or "")[:400],
                "url": a.get("url", ""),
                "published_at": published_at,
            })
        log.debug("Fetched %d articles from NewsAPI", len(articles))
        return articles
    except Exception as e:
        log.warning("NewsAPI fetch failed: %s", e)
        return []


def fetch_all() -> int:
    """Fetch from all sources, filter stale, persist to raw_articles. Returns count saved.

    Deduplication is handled at the database level via the title_hash UNIQUE constraint
    in raw_articles — no need to track seen hashes in memory across poll cycles.
    """
    articles = fetch_rss() + fetch_newsapi()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_ARTICLE_AGE_HOURS)

    fresh = []
    stale = 0
    for a in articles:
        if not a["title"]:
            continue
        if a["published_at"] < cutoff:
            stale += 1
            continue
        fresh.append(a)

    saved = storage.save_raw_articles(fresh)
    log.info(
        "Fetched %d articles from %d total (%d stale discarded, %d new saved to raw_articles)",
        len(fresh), len(articles), stale, saved,
    )
    return saved
