"""Tests for core/feeds.py — fetch_all() filtering logic."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from core import feeds, config


def _rss_article(title="Market Update", age_hours=1):
    published_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return {
        "source": "Reuters",
        "title": title,
        "summary": "A summary.",
        "url": "https://example.com/1",
        "published_at": published_at,
    }


class TestFetchAllFiltering:
    def test_fresh_article_is_saved(self):
        article = _rss_article("Fresh Headline", age_hours=1)
        with patch.object(feeds, "fetch_rss", return_value=[article]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=1) as mock_save:
            count = feeds.fetch_all()
        assert count == 1
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 1
        assert saved[0]["title"] == "Fresh Headline"

    def test_stale_article_is_discarded(self):
        # MAX_ARTICLE_AGE_HOURS default is typically 24; use well beyond that
        stale = _rss_article("Old News", age_hours=config.MAX_ARTICLE_AGE_HOURS + 2)
        with patch.object(feeds, "fetch_rss", return_value=[stale]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=0) as mock_save:
            count = feeds.fetch_all()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 0

    def test_empty_title_is_discarded(self):
        article = _rss_article(title="", age_hours=1)
        with patch.object(feeds, "fetch_rss", return_value=[article]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=0) as mock_save:
            feeds.fetch_all()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 0

    def test_whitespace_only_title_is_discarded(self):
        article = _rss_article(title="   ", age_hours=1)
        # feeds.py strips title in fetch_rss; simulate post-strip empty
        article["title"] = ""
        with patch.object(feeds, "fetch_rss", return_value=[article]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=0) as mock_save:
            feeds.fetch_all()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 0

    def test_mix_of_fresh_and_stale(self):
        fresh = _rss_article("Fresh", age_hours=2)
        stale = _rss_article("Stale", age_hours=config.MAX_ARTICLE_AGE_HOURS + 5)
        with patch.object(feeds, "fetch_rss", return_value=[fresh, stale]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=1) as mock_save:
            feeds.fetch_all()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 1
        assert saved[0]["title"] == "Fresh"

    def test_returns_count_from_storage(self):
        articles = [_rss_article(f"Headline {i}", age_hours=1) for i in range(3)]
        with patch.object(feeds, "fetch_rss", return_value=articles), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=3):
            result = feeds.fetch_all()
        assert result == 3

    def test_empty_feeds_returns_zero(self):
        with patch.object(feeds, "fetch_rss", return_value=[]), \
             patch.object(feeds, "fetch_newsapi", return_value=[]), \
             patch("core.feeds.storage.save_raw_articles", return_value=0):
            result = feeds.fetch_all()
        assert result == 0

    def test_newsapi_articles_combined(self):
        rss_article = _rss_article("RSS Headline", age_hours=1)
        newsapi_article = _rss_article("NewsAPI Headline", age_hours=1)
        newsapi_article["source"] = "NewsAPI"
        with patch.object(feeds, "fetch_rss", return_value=[rss_article]), \
             patch.object(feeds, "fetch_newsapi", return_value=[newsapi_article]), \
             patch("core.feeds.storage.save_raw_articles", return_value=2) as mock_save:
            feeds.fetch_all()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 2


class TestParseTime:
    def test_parses_published_parsed(self):
        from core.feeds import _parse_time
        entry = {"published_parsed": (2026, 4, 15, 10, 30, 0, 1, 105, 0)}
        result = _parse_time(entry)
        assert result == datetime(2026, 4, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_falls_back_to_updated_parsed(self):
        from core.feeds import _parse_time
        entry = {"published_parsed": None, "updated_parsed": (2026, 3, 1, 8, 0, 0, 0, 60, 0)}
        result = _parse_time(entry)
        assert result == datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)

    def test_returns_now_when_no_date(self):
        from core.feeds import _parse_time
        before = datetime.now(timezone.utc)
        result = _parse_time({"published_parsed": None, "updated_parsed": None})
        after = datetime.now(timezone.utc)
        assert before <= result <= after

    def test_returns_now_on_exception(self):
        from core.feeds import _parse_time
        entry = {"published_parsed": "not-a-tuple"}
        before = datetime.now(timezone.utc)
        result = _parse_time(entry)
        after = datetime.now(timezone.utc)
        assert before <= result <= after


class TestFetchRss:
    def _make_entry(self, title="Test", summary="Summary", link="https://ex.com"):
        from unittest.mock import MagicMock
        entry = MagicMock()
        entry.get = lambda k, d="": {
            "title": title,
            "summary": summary,
            "link": link,
            "published_parsed": (2026, 4, 15, 10, 0, 0, 1, 105, 0),
        }.get(k, d)
        return entry

    def test_returns_articles_from_feed(self):
        entry = self._make_entry("Market Update")
        mock_feed = MagicMock()
        mock_feed.feed = MagicMock()
        mock_feed.feed.get = lambda k, d="": {"title": "Reuters"}.get(k, d)
        mock_feed.entries = [entry]
        with patch("core.feeds.feedparser.parse", return_value=mock_feed), \
             patch("core.feeds.config.RSS_FEEDS", ["https://fake.rss/feed"]):
            articles = feeds.fetch_rss()
        assert len(articles) == 1
        assert articles[0]["title"] == "Market Update"
        assert articles[0]["source"] == "Reuters"

    def test_skips_failed_feed_gracefully(self):
        with patch("core.feeds.feedparser.parse", side_effect=Exception("connection error")), \
             patch("core.feeds.config.RSS_FEEDS", ["https://bad.rss/feed"]):
            articles = feeds.fetch_rss()
        assert articles == []


class TestNewsApiRateLimiting:
    def test_rate_ok_when_no_history(self):
        from core.feeds import _newsapi_rate_ok
        with patch("core.feeds.storage.get_meta", return_value=None), \
             patch("core.feeds.config.NEWSAPI_DAILY_LIMIT", 95):
            assert _newsapi_rate_ok() is True

    def test_rate_blocked_when_daily_limit_reached(self):
        from core.feeds import _newsapi_rate_ok
        def mock_meta(key):
            if key.startswith("newsapi_count_"):
                return "95"
            return None
        with patch("core.feeds.storage.get_meta", side_effect=mock_meta), \
             patch("core.feeds.config.NEWSAPI_DAILY_LIMIT", 95):
            assert _newsapi_rate_ok() is False

    def test_rate_blocked_within_cooldown(self):
        from core.feeds import _newsapi_rate_ok
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        def mock_meta(key):
            if key.startswith("newsapi_count_"):
                return "0"
            if key == "newsapi_last_fetch":
                return recent
            return None
        with patch("core.feeds.storage.get_meta", side_effect=mock_meta), \
             patch("core.feeds.config.NEWSAPI_DAILY_LIMIT", 95), \
             patch("core.feeds.config.NEWSAPI_MIN_INTERVAL_SECONDS", 900):
            assert _newsapi_rate_ok() is False

    def test_fetch_newsapi_skips_when_no_key(self):
        with patch("core.feeds.config.NEWSAPI_KEY", None):
            result = feeds.fetch_newsapi()
        assert result == []
