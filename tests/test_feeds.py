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
