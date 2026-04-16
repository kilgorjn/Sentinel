"""Tests for core/monitor.py — classify_pending() cursor and failure behavior."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, call, MagicMock

from core import monitor, spike_detector, storage


def _article(id=1, title="Fed Cuts Rates"):
    return {
        "id": id,
        "title": title,
        "source": "Reuters",
        "url": f"https://example.com/{id}",
        "summary": "A summary.",
        "published_at": datetime.now(timezone.utc),
    }


def _result(classification="LOW"):
    return {
        "classification": classification,
        "confidence": 0.8,
        "reason": "Test reason",
        "sentiment": "NEUTRAL",
    }


@pytest.fixture
def detector():
    return spike_detector.SpikeDetector(window_minutes=30, threshold=3)


class TestClassifyPending:
    def test_returns_zero_when_no_articles(self, detector):
        with patch("core.monitor.storage.get_unclassified_articles", return_value=[]):
            count = monitor.classify_pending(detector)
        assert count == 0

    def test_classifies_one_article(self, detector):
        article = _article(1, "Market Rally")
        result = _result("LOW")
        with patch("core.monitor.storage.get_unclassified_articles", return_value=[article]), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value=result), \
             patch("core.monitor.storage.save_event", return_value=True), \
             patch("core.monitor.storage.advance_cursor") as mock_advance, \
             patch("core.monitor.alerts.alert_article"), \
             patch("time.sleep"):
            count = monitor.classify_pending(detector)
        assert count == 1
        mock_advance.assert_called_once_with(1)

    def test_skips_already_seen_and_advances_cursor(self, detector):
        article = _article(1, "Known Headline")
        with patch("core.monitor.storage.get_unclassified_articles", return_value=[article]), \
             patch("core.monitor.storage.already_seen", return_value=True), \
             patch("core.monitor.classifier.classify") as mock_classify, \
             patch("core.monitor.storage.advance_cursor") as mock_advance, \
             patch("time.sleep"):
            count = monitor.classify_pending(detector)
        # Should skip classification but advance cursor
        mock_classify.assert_not_called()
        mock_advance.assert_called_once_with(1)
        assert count == 0

    def test_breaks_on_save_failure(self, detector):
        articles = [_article(i, f"Headline {i}") for i in range(1, 4)]
        results = [_result("LOW")] * 3

        with patch("core.monitor.storage.get_unclassified_articles", return_value=articles), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", side_effect=results), \
             patch("core.monitor.storage.save_event", side_effect=[False, True, True]), \
             patch("core.monitor.storage.advance_cursor") as mock_advance, \
             patch("core.monitor.alerts.alert_article"), \
             patch("time.sleep"):
            count = monitor.classify_pending(detector)
        # Breaks after first failure — cursor never advances
        mock_advance.assert_not_called()
        assert count == 0

    def test_advances_cursor_per_article(self, detector):
        articles = [_article(i, f"Headline {i}") for i in range(1, 4)]
        with patch("core.monitor.storage.get_unclassified_articles", return_value=articles), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value=_result()), \
             patch("core.monitor.storage.save_event", return_value=True), \
             patch("core.monitor.storage.advance_cursor") as mock_advance, \
             patch("core.monitor.alerts.alert_article"), \
             patch("time.sleep"):
            count = monitor.classify_pending(detector)
        assert count == 3
        mock_advance.assert_has_calls([call(1), call(2), call(3)])

    def test_alert_fires_after_save(self, detector):
        """Alert must fire only after successful save_event, not before."""
        call_order = []
        article = _article(1)

        def fake_save(a, r):
            call_order.append("save")
            return True

        def fake_alert(a, r):
            call_order.append("alert")

        with patch("core.monitor.storage.get_unclassified_articles", return_value=[article]), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value=_result()), \
             patch("core.monitor.storage.save_event", side_effect=fake_save), \
             patch("core.monitor.storage.advance_cursor"), \
             patch("core.monitor.alerts.alert_article", side_effect=fake_alert), \
             patch("time.sleep"):
            monitor.classify_pending(detector)

        assert call_order == ["save", "alert"]

    def test_high_event_recorded_in_detector(self, detector):
        article = _article(1, "Market Crash")
        with patch("core.monitor.storage.get_unclassified_articles", return_value=[article]), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value=_result("HIGH")), \
             patch("core.monitor.storage.save_event", return_value=True), \
             patch("core.monitor.storage.advance_cursor"), \
             patch("core.monitor.alerts.alert_article"), \
             patch("time.sleep"):
            monitor.classify_pending(detector)
        assert detector.current_count() == 1

    def test_surge_alert_fires_at_threshold(self, detector):
        articles = [_article(i, f"Crash {i}") for i in range(1, 4)]
        with patch("core.monitor.storage.get_unclassified_articles", return_value=articles), \
             patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value=_result("HIGH")), \
             patch("core.monitor.storage.save_event", return_value=True), \
             patch("core.monitor.storage.advance_cursor"), \
             patch("core.monitor.alerts.alert_article"), \
             patch("core.monitor.alerts.alert_surge") as mock_surge, \
             patch("time.sleep"):
            monitor.classify_pending(detector)
        mock_surge.assert_called_once()
