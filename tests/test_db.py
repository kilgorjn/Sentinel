"""Tests for core/db.py — model to_dict() datetime serialization."""

import pytest
from datetime import datetime, timezone

from core.db import RawArticle, NewsEvent, Feed, MarketSnapshot


_NOW = datetime(2026, 4, 14, 12, 0, 0)  # naive — simulates what MySQL returns


class TestNewsEventToDict:
    def test_published_at_has_utc_offset(self):
        event = NewsEvent(
            title="Test",
            source="Reuters",
            url="https://example.com",
            published_at=_NOW,
            classification="HIGH",
            confidence=0.9,
            reason="Reason",
            sentiment="NEUTRAL",
            created_at=_NOW,
        )
        d = event.to_dict()
        assert d["published_at"].endswith("+00:00"), (
            f"Expected +00:00 suffix, got: {d['published_at']}"
        )

    def test_created_at_has_utc_offset(self):
        event = NewsEvent(
            title="Test",
            published_at=_NOW,
            classification="LOW",
            created_at=_NOW,
        )
        d = event.to_dict()
        assert d["created_at"].endswith("+00:00")

    def test_none_published_at_returns_none(self):
        event = NewsEvent(
            title="Test",
            published_at=None,
            classification="LOW",
            created_at=_NOW,
        )
        d = event.to_dict()
        assert d["published_at"] is None

    def test_fields_present(self):
        event = NewsEvent(
            title="T", published_at=_NOW, classification="LOW", created_at=_NOW
        )
        d = event.to_dict()
        for key in ("id", "title", "source", "url", "published_at", "classification",
                    "confidence", "reason", "sentiment", "actual_impact", "created_at"):
            assert key in d


class TestFeedToDict:
    def test_added_at_has_utc_offset(self):
        feed = Feed(
            id="abc123",
            url="https://feeds.example.com/rss",
            url_hash="a" * 64,
            name="Example Feed",
            active=True,
            added_at=_NOW,
        )
        d = feed.to_dict()
        assert d["added_at"].endswith("+00:00")

    def test_url_hash_not_in_dict(self):
        feed = Feed(
            id="abc123",
            url="https://feeds.example.com/rss",
            url_hash="a" * 64,
            name="Example Feed",
            added_at=_NOW,
        )
        d = feed.to_dict()
        assert "url_hash" not in d

    def test_none_added_at_returns_none(self):
        feed = Feed(id="x", url="u", url_hash="h", name="n", added_at=None)
        d = feed.to_dict()
        assert d["added_at"] is None


class TestMarketSnapshotToDict:
    def test_fetched_at_has_utc_offset(self):
        snap = MarketSnapshot(
            symbol="SPX",
            name="S&P 500",
            region="US",
            price=5000.0,
            prev_close=4950.0,
            change_pct=1.01,
            fetched_at=_NOW,
        )
        d = snap.to_dict()
        assert d["fetched_at"].endswith("+00:00")

    def test_none_fetched_at_returns_none(self):
        snap = MarketSnapshot(symbol="SPX", fetched_at=None)
        d = snap.to_dict()
        assert d["fetched_at"] is None


class TestRawArticleToDict:
    def test_published_at_is_datetime_not_string(self):
        """RawArticle.to_dict() must return raw datetime for internal pipeline use."""
        article = RawArticle(
            title_hash="a" * 64,
            title="Test",
            source="Reuters",
            url="https://example.com",
            published_at=_NOW,
            fetched_at=_NOW,
        )
        d = article.to_dict()
        assert isinstance(d["published_at"], datetime), (
            "published_at should be a datetime object, not a string"
        )

    def test_fetched_at_is_datetime_not_string(self):
        article = RawArticle(
            title_hash="b" * 64,
            title="Test",
            fetched_at=_NOW,
        )
        d = article.to_dict()
        assert isinstance(d["fetched_at"], datetime)
