"""Feed format handlers and type detection for RSS/Atom feeds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Any
import logging
import feedparser

log = logging.getLogger(__name__)


class FeedHandler(ABC):
    """Abstract base for feed format handlers."""

    supported_versions: list[str] = []

    @abstractmethod
    def extract_article(self, entry: dict) -> dict:
        """Extract normalized article data from a feed entry.

        Returns dict with keys: title, summary, url, published_at
        """
        pass

    @classmethod
    def can_handle(cls, feed_version: str) -> bool:
        """Check if this handler supports the feed version."""
        return feed_version in cls.supported_versions


class RSS20Handler(FeedHandler):
    """Handler for RSS 2.0 feeds."""

    supported_versions = ["rss20", "rss091n", "rss092", "rss093", "rss094"]

    def extract_article(self, entry: dict) -> dict:
        """Extract from RSS 2.0 entry."""
        return {
            "title": entry.get("title", "").strip(),
            "summary": (entry.get("summary") or entry.get("description") or "")[:400],
            "url": entry.get("link", ""),
            "published_at": self._parse_time(entry),
        }

    @staticmethod
    def _parse_time(entry) -> datetime:
        """Extract published datetime from RSS entry."""
        try:
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t:
                return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            pass
        return datetime.now(timezone.utc)


class AtomHandler(FeedHandler):
    """Handler for Atom feeds."""

    supported_versions = ["atom10", "atom03"]

    def extract_article(self, entry: dict) -> dict:
        """Extract from Atom entry."""
        # Atom uses 'summary' and 'content'
        summary = entry.get("summary") or entry.get("content", [{}])[0].get("value") or ""
        return {
            "title": entry.get("title", "").strip(),
            "summary": summary[:400] if summary else "",
            "url": entry.get("link", "") or (entry.get("links", [{}])[0].get("href") if entry.get("links") else ""),
            "published_at": self._parse_time(entry),
        }

    @staticmethod
    def _parse_time(entry) -> datetime:
        """Extract published datetime from Atom entry."""
        try:
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t:
                return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            pass
        return datetime.now(timezone.utc)


# Registry of all handlers
_HANDLERS = [RSS20Handler(), AtomHandler()]


def get_handler(feed_version: str) -> Optional[FeedHandler]:
    """Get the appropriate handler for a feed version."""
    for handler in _HANDLERS:
        if handler.can_handle(feed_version):
            return handler
    return None


def detect_feed_type(feed_url: str) -> dict[str, Any]:
    """Detect feed type and return metadata.

    Returns dict with keys:
      valid: bool
      feed_type: str (e.g. "RSS 2.0", "Atom 1.0")
      version: str (e.g. "rss20", "atom10")
      entry_count: int
      handler: FeedHandler or None
      sample_entries: list of dicts with title, summary_length, has_timestamp
      errors: list of error messages
    """
    result: dict[str, Any] = {
        "valid": False,
        "feed_type": None,
        "version": None,
        "entry_count": 0,
        "handler": None,
        "sample_entries": [],
        "errors": [],
    }

    try:
        feed = feedparser.parse(feed_url)
        version = feed.get("version", "unknown")
        result["version"] = version

        # Map version to human-readable name
        version_names = {
            "rss20": "RSS 2.0",
            "rss091n": "RSS 0.91",
            "rss092": "RSS 0.92",
            "rss093": "RSS 0.93",
            "rss094": "RSS 0.94",
            "atom10": "Atom 1.0",
            "atom03": "Atom 0.3",
        }
        result["feed_type"] = version_names.get(version, f"Unknown ({version})")

        # Get handler
        handler = get_handler(version)
        if not handler:
            result["errors"].append(
                f"Feed type '{result['feed_type']}' is not supported. "
                f"Supported: RSS 2.0, Atom 1.0"
            )
            return result

        result["handler"] = handler

        # Check entries
        entries = feed.get("entries", [])
        result["entry_count"] = len(entries)

        if not entries:
            result["errors"].append("Feed has no entries")
            return result

        # Sample first 3 entries
        for entry in entries[:3]:
            try:
                article = handler.extract_article(entry)
                result["sample_entries"].append({
                    "title": article["title"][:60] + ("..." if len(article["title"]) > 60 else ""),
                    "summary_length": len(article["summary"]),
                    "has_timestamp": article["published_at"] is not None,
                    "has_url": bool(article["url"]),
                })
            except Exception as e:
                result["errors"].append(f"Failed to parse entry: {str(e)}")

        # Validation checks
        if result["entry_count"] == 0:
            result["errors"].append("No entries found in feed")
        elif not result["sample_entries"]:
            result["errors"].append("Could not extract any sample entries")
        else:
            # Check if entries have summaries
            has_summaries = any(
                e["summary_length"] > 50 for e in result["sample_entries"]
            )
            if not has_summaries:
                result["errors"].append(
                    "Feed entries have no summaries (titles only). "
                    "Classifier will have limited context."
                )

        # If no errors, mark as valid
        if not result["errors"]:
            result["valid"] = True

        return result

    except Exception as e:
        result["errors"].append(f"Failed to fetch/parse feed: {str(e)}")
        return result


def get_supported_types() -> list[str]:
    """Return list of supported feed types."""
    return [
        "RSS 2.0 (RSS 0.91, 0.92, 0.93, 0.94)",
        "Atom 1.0 (Atom 0.3)",
    ]
