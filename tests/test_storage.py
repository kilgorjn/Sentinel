"""Tests for core/storage.py — raw article pipeline and save_event."""

import pytest
from datetime import datetime, timezone, timedelta
from core import storage


def _article(title="Test Article", source="Reuters", url="https://example.com/1",
              published_at=None):
    return {
        "title": title,
        "source": source,
        "url": url,
        "summary": "A test summary.",
        "published_at": published_at or datetime.now(timezone.utc),
    }


def _result(classification="LOW", confidence=0.8, reason="Test reason", sentiment="NEUTRAL"):
    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
        "sentiment": sentiment,
    }


class TestSaveRawArticles:
    def test_inserts_new_article(self):
        count = storage.save_raw_articles([_article("Unique Title A")])
        assert count == 1

    def test_returns_zero_for_empty_list(self):
        assert storage.save_raw_articles([]) == 0

    def test_deduplicates_same_title(self):
        article = _article("Duplicate Title")
        storage.save_raw_articles([article])
        count = storage.save_raw_articles([article])
        assert count == 0

    def test_deduplicates_case_insensitive(self):
        storage.save_raw_articles([_article("Markets Rise")])
        count = storage.save_raw_articles([_article("MARKETS RISE")])
        assert count == 0

    def test_deduplicates_punctuation_difference(self):
        storage.save_raw_articles([_article("Markets Rise!")])
        count = storage.save_raw_articles([_article("Markets Rise")])
        assert count == 0

    def test_skips_empty_title(self):
        count = storage.save_raw_articles([_article(title="")])
        assert count == 0

    def test_inserts_multiple_distinct_articles(self):
        articles = [_article(f"Title {i}", url=f"https://example.com/{i}") for i in range(5)]
        count = storage.save_raw_articles(articles)
        assert count == 5

    def test_partial_duplicates_in_batch(self):
        storage.save_raw_articles([_article("Existing Article")])
        batch = [_article("Existing Article"), _article("New Article")]
        count = storage.save_raw_articles(batch)
        assert count == 1


class TestCursor:
    def test_first_run_returns_all_articles(self):
        storage.save_raw_articles([_article("Article One"), _article("Article Two")])
        results = storage.get_unclassified_articles()
        assert len(results) == 2

    def test_advance_cursor_excludes_processed(self):
        storage.save_raw_articles([_article("Article One")])
        articles = storage.get_unclassified_articles()
        assert len(articles) == 1
        storage.advance_cursor(articles[0]["id"])

        remaining = storage.get_unclassified_articles()
        assert len(remaining) == 0

    def test_new_articles_after_cursor_are_returned(self):
        storage.save_raw_articles([_article("Old Article")])
        articles = storage.get_unclassified_articles()
        storage.advance_cursor(articles[0]["id"])

        storage.save_raw_articles([_article("New Article")])
        results = storage.get_unclassified_articles()
        assert len(results) == 1
        assert results[0]["title"] == "New Article"

    def test_invalid_cursor_resets_to_zero(self):
        storage.set_meta(storage.CURSOR_KEY, "not-a-number")
        storage.save_raw_articles([_article("Some Article")])
        results = storage.get_unclassified_articles()
        assert len(results) == 1

    def test_batch_size_respected(self):
        articles = [_article(f"Article {i}", url=f"https://example.com/{i}") for i in range(10)]
        storage.save_raw_articles(articles)
        results = storage.get_unclassified_articles(batch_size=3)
        assert len(results) == 3

    def test_cursor_ordered_by_id(self):
        storage.save_raw_articles([
            _article("First", url="https://example.com/1"),
            _article("Second", url="https://example.com/2"),
            _article("Third", url="https://example.com/3"),
        ])
        results = storage.get_unclassified_articles()
        ids = [r["id"] for r in results]
        assert ids == sorted(ids)


class TestSaveEvent:
    def test_returns_true_on_success(self):
        ok = storage.save_event(_article("Fed Cuts Rates"), _result("HIGH"))
        assert ok is True

    def test_event_appears_in_summary(self):
        storage.save_event(_article("Market Drop"), _result("HIGH"))
        rows = storage.summary()
        counts = {r["classification"]: r["count"] for r in rows}
        assert counts.get("HIGH", 0) >= 1

    def test_truncates_long_title(self):
        long_title = "A" * 600
        ok = storage.save_event(_article(title=long_title), _result())
        assert ok is True

    def test_truncates_long_reason(self):
        long_reason = "B" * 600
        ok = storage.save_event(_article(), _result(reason=long_reason))
        assert ok is True

    def test_truncates_long_url(self):
        long_url = "https://example.com/" + "x" * 1100
        ok = storage.save_event(_article(url=long_url), _result())
        assert ok is True


class TestAlreadySeen:
    def test_false_for_new_title(self):
        assert storage.already_seen("Brand New Headline") is False

    def test_true_after_save(self):
        storage.save_event(_article("Known Headline"), _result())
        assert storage.already_seen("Known Headline") is True

    def test_case_sensitive(self):
        storage.save_event(_article("Known Headline"), _result())
        assert storage.already_seen("known headline") is False


class TestMeta:
    def test_get_missing_key_returns_none(self):
        assert storage.get_meta("nonexistent_key") is None

    def test_set_and_get(self):
        storage.set_meta("test_key", "test_value")
        assert storage.get_meta("test_key") == "test_value"

    def test_update_existing(self):
        storage.set_meta("test_key", "old")
        storage.set_meta("test_key", "new")
        assert storage.get_meta("test_key") == "new"


class TestFeedStorage:
    def test_load_feeds_empty(self):
        assert storage.load_feeds() == []

    def test_add_and_load_feed(self):
        ok = storage.add_feed("rss1", "https://feeds.example.com/rss", "Example", "RSS 2.0")
        assert ok is True
        feeds = storage.load_feeds()
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://feeds.example.com/rss"

    def test_add_duplicate_url_returns_false(self):
        storage.add_feed("rss1", "https://feeds.example.com/rss", "Example", "RSS 2.0")
        ok = storage.add_feed("rss2", "https://feeds.example.com/rss", "Duplicate", "RSS 2.0")
        assert ok is False

    def test_delete_feed(self):
        storage.add_feed("del1", "https://del.example.com/rss", "Del Feed", "RSS 2.0")
        assert storage.delete_feed("del1") is True
        assert storage.load_feeds() == []

    def test_delete_nonexistent_returns_false(self):
        assert storage.delete_feed("no-such-id") is False

    def test_toggle_feed_inactive(self):
        storage.add_feed("tog1", "https://tog.example.com/rss", "Toggle Feed", "RSS 2.0")
        result = storage.toggle_feed("tog1", False)
        assert result is not None
        assert result["active"] is False
        assert storage.load_feeds(active_only=True) == []

    def test_toggle_feed_active(self):
        storage.add_feed("tog2", "https://tog2.example.com/rss", "Toggle Feed 2", "RSS 2.0")
        storage.toggle_feed("tog2", False)
        result = storage.toggle_feed("tog2", True)
        assert result["active"] is True
        assert len(storage.load_feeds(active_only=True)) == 1

    def test_toggle_nonexistent_returns_none(self):
        assert storage.toggle_feed("no-such-id", True) is None

    def test_load_feeds_active_only_false_returns_all(self):
        storage.add_feed("a1", "https://active.example.com/rss", "Active", "RSS 2.0")
        storage.add_feed("a2", "https://inactive.example.com/rss", "Inactive", "RSS 2.0")
        storage.toggle_feed("a2", False)
        assert len(storage.load_feeds(active_only=False)) == 2


class TestMarketData:
    def _snapshot(self, symbol="SPX", change_pct=1.0, fetched_offset_seconds=0):
        from datetime import timedelta
        fetched_at = datetime.now(timezone.utc) - timedelta(seconds=fetched_offset_seconds)
        return {
            "symbol": symbol,
            "name": f"{symbol} Index",
            "region": "us",
            "price": 5000.0,
            "prev_close": 4950.0,
            "change_pct": change_pct,
            "high": 5010.0,
            "low": 4940.0,
            "fetched_at": fetched_at.isoformat(),
        }

    def test_save_and_retrieve_snapshots(self):
        storage.save_snapshots([self._snapshot("SPX")])
        results = storage.get_latest_market_data()
        assert len(results) == 1
        assert results[0]["symbol"] == "SPX"

    def test_get_latest_returns_most_recent_per_symbol(self):
        storage.save_snapshots([self._snapshot("SPX", fetched_offset_seconds=60)])
        storage.save_snapshots([self._snapshot("SPX", change_pct=2.0, fetched_offset_seconds=0)])
        results = storage.get_latest_market_data()
        assert len(results) == 1
        assert results[0]["change_pct"] == 2.0

    def test_save_snapshots_empty_list(self):
        storage.save_snapshots([])
        assert storage.get_latest_market_data() == []

    def test_get_market_history_returns_within_window(self):
        storage.save_snapshots([self._snapshot("NDX")])
        results = storage.get_market_history("NDX", hours=1)
        assert len(results) == 1

    def test_get_market_history_excludes_old(self):
        from datetime import timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        snap = self._snapshot("NDX")
        snap["fetched_at"] = old_time
        storage.save_snapshots([snap])
        assert storage.get_market_history("NDX", hours=1) == []

    def test_get_market_history_filters_by_symbol(self):
        storage.save_snapshots([self._snapshot("SPX"), self._snapshot("NDX")])
        results = storage.get_market_history("SPX", hours=1)
        assert all(r["symbol"] == "SPX" for r in results)
