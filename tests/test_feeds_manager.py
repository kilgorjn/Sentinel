"""Tests for core/feeds_manager.py — CRUD wrappers over storage."""

import pytest
from unittest.mock import patch

from core import feeds_manager, storage


@pytest.fixture(autouse=True)
def no_json_migration():
    with patch("core.feeds_manager._migrate_feeds_from_json"):
        yield


class TestLoadFeeds:
    def test_returns_empty_when_no_feeds_and_no_defaults(self):
        with patch("core.feeds_manager._ensure_default_feeds"):
            result = feeds_manager.load_feeds()
        assert result == []

    def test_creates_defaults_when_db_empty(self):
        result = feeds_manager.load_feeds()
        assert len(result) == 3

    def test_returns_only_active_feeds(self):
        storage.add_feed("f1", "https://feeds.example.com/a", "Feed A", "RSS 2.0")
        storage.add_feed("f2", "https://feeds.example.com/b", "Feed B", "RSS 2.0")
        storage.toggle_feed("f2", False)
        with patch("core.feeds_manager._ensure_default_feeds"):
            result = feeds_manager.load_feeds()
        urls = [f["url"] for f in result]
        assert "https://feeds.example.com/a" in urls
        assert "https://feeds.example.com/b" not in urls


class TestGetAllFeeds:
    def test_returns_active_and_inactive(self):
        storage.add_feed("f1", "https://feeds.example.com/a", "Feed A", "RSS 2.0")
        storage.add_feed("f2", "https://feeds.example.com/b", "Feed B", "RSS 2.0")
        storage.toggle_feed("f2", False)
        with patch("core.feeds_manager._ensure_default_feeds"):
            result = feeds_manager.get_all_feeds()
        assert len(result) == 2


class TestAddFeed:
    def test_adds_new_feed(self):
        with patch("core.feeds_manager._ensure_default_feeds"):
            feed = feeds_manager.add_feed("https://feeds.new.com/rss", "New Feed", "RSS 2.0")
        assert feed["url"] == "https://feeds.new.com/rss"
        assert feed["name"] == "New Feed"
        assert "id" in feed

    def test_raises_on_duplicate_url(self):
        storage.add_feed("existing", "https://dup.example.com/rss", "Existing", "RSS 2.0")
        with pytest.raises(ValueError, match="already exists"):
            feeds_manager.add_feed("https://dup.example.com/rss", "Duplicate", "RSS 2.0")

    def test_returned_feed_has_expected_fields(self):
        with patch("core.feeds_manager._ensure_default_feeds"):
            feed = feeds_manager.add_feed("https://fields.example.com/rss", "Fields Feed", "Atom 1.0")
        for key in ("id", "url", "name", "feed_type", "active"):
            assert key in feed
        assert feed["active"] is True


class TestDeleteFeed:
    def test_deletes_existing_feed(self):
        storage.add_feed("del1", "https://del.example.com/rss", "Del Feed", "RSS 2.0")
        result = feeds_manager.delete_feed("del1")
        assert result is True

    def test_returns_false_for_unknown_id(self):
        result = feeds_manager.delete_feed("nonexistent-id")
        assert result is False


class TestToggleFeed:
    def test_deactivates_feed(self):
        storage.add_feed("tog1", "https://tog.example.com/rss", "Toggle Feed", "RSS 2.0")
        result = feeds_manager.toggle_feed("tog1", False)
        assert result is not None
        assert result["active"] is False

    def test_reactivates_feed(self):
        storage.add_feed("tog2", "https://tog2.example.com/rss", "Toggle Feed 2", "RSS 2.0")
        storage.toggle_feed("tog2", False)
        result = feeds_manager.toggle_feed("tog2", True)
        assert result["active"] is True

    def test_returns_none_for_unknown_id(self):
        result = feeds_manager.toggle_feed("nonexistent-id", True)
        assert result is None


class TestGetFeedUrls:
    def test_returns_list_of_urls(self):
        storage.add_feed("u1", "https://url1.example.com/rss", "URL Feed 1", "RSS 2.0")
        storage.add_feed("u2", "https://url2.example.com/rss", "URL Feed 2", "RSS 2.0")
        with patch("core.feeds_manager._ensure_default_feeds"):
            urls = feeds_manager.get_feed_urls()
        assert "https://url1.example.com/rss" in urls
        assert "https://url2.example.com/rss" in urls

    def test_excludes_inactive_urls(self):
        storage.add_feed("u3", "https://active.example.com/rss", "Active", "RSS 2.0")
        storage.add_feed("u4", "https://inactive.example.com/rss", "Inactive", "RSS 2.0")
        storage.toggle_feed("u4", False)
        with patch("core.feeds_manager._ensure_default_feeds"):
            urls = feeds_manager.get_feed_urls()
        assert "https://active.example.com/rss" in urls
        assert "https://inactive.example.com/rss" not in urls
