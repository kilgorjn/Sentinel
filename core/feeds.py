"""Fetch and parse financial news from RSS feeds and optionally NewsAPI."""

import re
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from . import config

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
    for url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
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


def fetch_newsapi() -> list[dict]:
    """Fetch from NewsAPI if configured."""
    if not config.NEWSAPI_KEY:
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


def fetch_all() -> list[dict]:
    """Fetch from all sources, deduplicate, filter stale, return sorted newest-first."""
    articles = fetch_rss() + fetch_newsapi()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_ARTICLE_AGE_HOURS)

    # Deduplicate by normalized title fingerprint and drop articles older than MAX_ARTICLE_AGE_HOURS
    seen: set[str] = set()
    unique = []
    stale = 0
    for a in articles:
        if not a["title"]:
            continue
        if a["published_at"] < cutoff:
            stale += 1
            continue
        key = _normalize_title(a["title"])
        fp = hashlib.md5(key.encode()).hexdigest()
        if fp not in seen:
            seen.add(fp)
            unique.append(a)

    unique.sort(key=lambda x: x["published_at"], reverse=True)
    log.info("Fetched %d unique articles from %d total (%d stale discarded)", len(unique), len(articles), stale)
    return unique
