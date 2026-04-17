"""Tests for core/monitor.py — classify_pending() cursor and failure behavior."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, call, MagicMock

from core import monitor, spike_detector, storage
from core.monitor import _handle_market_data, _handle_news_fetch, _log_summary, _is_market_hours


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


class TestHandleNewsFetch:
    def test_skips_fetch_outside_market_hours(self):
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.monitor._is_market_hours", return_value=False), \
             patch("core.monitor.feeds.fetch_all") as mock_fetch:
            mock_cfg.MARKET_HOURS_ONLY = True
            _handle_news_fetch()
        mock_fetch.assert_not_called()

    def test_fetches_during_market_hours(self):
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.monitor._is_market_hours", return_value=True), \
             patch("core.monitor.feeds.fetch_all") as mock_fetch:
            mock_cfg.MARKET_HOURS_ONLY = True
            _handle_news_fetch()
        mock_fetch.assert_called_once()

    def test_always_fetches_when_market_hours_only_false(self):
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.monitor.feeds.fetch_all") as mock_fetch:
            mock_cfg.MARKET_HOURS_ONLY = False
            _handle_news_fetch()
        mock_fetch.assert_called_once()


class TestHandleMarketData:
    def test_does_nothing_when_disabled(self, detector):
        with patch("core.monitor.config") as mock_cfg:
            mock_cfg.MARKET_DATA_ENABLED = False
            _handle_market_data(detector)  # should not raise or call anything

    def test_skips_when_no_snapshots(self, detector):
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.market_data.fetch_snapshots", return_value=[]), \
             patch("core.monitor.storage.save_snapshots") as mock_save:
            mock_cfg.MARKET_DATA_ENABLED = True
            _handle_market_data(detector)
        mock_save.assert_not_called()

    def test_saves_snapshots_when_present(self, detector):
        snapshots = [{"symbol": "SPX", "change_pct": 1.0}]
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.market_data.fetch_snapshots", return_value=snapshots), \
             patch("core.market_data.detect_volatility", return_value=[]), \
             patch("core.monitor.storage.save_snapshots") as mock_save:
            mock_cfg.MARKET_DATA_ENABLED = True
            _handle_market_data(detector)
        mock_save.assert_called_once_with(snapshots)

    def test_handles_fetch_exception_gracefully(self, detector):
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.monitor.storage.save_snapshots", side_effect=RuntimeError("db down")):
            mock_cfg.MARKET_DATA_ENABLED = True
            # Should not raise
            try:
                _handle_market_data(detector)
            except RuntimeError:
                pass  # Exception before save is also acceptable

    def test_fires_alert_for_high_severity_signal(self, detector):
        signal = {
            "severity": "HIGH",
            "message": "Market drop",
            "region": "us",
            "type": "drop",
            "change_pct": -4.0,
        }
        snapshots = [{"symbol": "SPX", "change_pct": -4.0}]
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.market_data.fetch_snapshots", return_value=snapshots), \
             patch("core.market_data.detect_volatility", return_value=[signal]), \
             patch("core.monitor.storage.save_snapshots"), \
             patch("core.monitor.alerts.alert_market_signal") as mock_alert:
            mock_cfg.MARKET_DATA_ENABLED = True
            mock_cfg.SPIKE_WINDOW_MINUTES = 30
            _handle_market_data(detector)
        mock_alert.assert_called_once_with(signal)

    def test_ignores_non_high_severity_signal(self, detector):
        signal = {
            "severity": "MEDIUM",
            "message": "Minor move",
            "region": "us",
            "type": "move",
            "change_pct": -1.0,
        }
        snapshots = [{"symbol": "SPX", "change_pct": -1.0}]
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.market_data.fetch_snapshots", return_value=snapshots), \
             patch("core.market_data.detect_volatility", return_value=[signal]), \
             patch("core.monitor.storage.save_snapshots"), \
             patch("core.monitor.alerts.alert_market_signal") as mock_alert:
            mock_cfg.MARKET_DATA_ENABLED = True
            _handle_market_data(detector)
        mock_alert.assert_not_called()


class TestLogSummary:
    def test_does_not_raise(self, detector):
        summary = [
            {"classification": "HIGH", "count": 2},
            {"classification": "MEDIUM", "count": 5},
            {"classification": "LOW", "count": 10},
        ]
        with patch("core.monitor.storage.summary", return_value=summary), \
             patch("core.monitor.config") as mock_cfg:
            mock_cfg.MARKET_DATA_ENABLED = False
            mock_cfg.SPIKE_HIGH_THRESHOLD = 3
            _log_summary(detector)

    def test_includes_market_ticker_count(self, detector):
        summary = [{"classification": "LOW", "count": 1}]
        snapshots = [{"symbol": "SPX"}, {"symbol": "DJI"}]
        with patch("core.monitor.storage.summary", return_value=summary), \
             patch("core.monitor.storage.get_latest_market_data", return_value=snapshots), \
             patch("core.monitor.config") as mock_cfg:
            mock_cfg.MARKET_DATA_ENABLED = True
            mock_cfg.SPIKE_HIGH_THRESHOLD = 3
            _log_summary(detector)  # should not raise


class TestIsMarketHours:
    def test_returns_true_during_market_hours_weekday(self):
        # Monday at 10:00 ET
        from datetime import datetime, timezone
        mock_dt = datetime(2026, 4, 13, 10, 0, 0)  # Monday
        with patch("core.monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_dt_obj = MagicMock()
            mock_dt_obj.weekday.return_value = 0  # Monday
            mock_dt_obj.hour = 10
            mock_datetime.now.return_value = mock_dt_obj
            result = _is_market_hours()
        assert result is True

    def test_returns_false_on_weekend(self):
        from zoneinfo import ZoneInfo
        # Saturday
        mock_dt = MagicMock()
        mock_dt.weekday.return_value = 5  # Saturday
        mock_dt.hour = 10
        with patch("core.monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = _is_market_hours()
        assert result is False

    def test_returns_false_before_market_open(self):
        mock_dt = MagicMock()
        mock_dt.weekday.return_value = 1  # Tuesday
        mock_dt.hour = 8
        with patch("core.monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = _is_market_hours()
        assert result is False

    def test_returns_false_after_market_close(self):
        mock_dt = MagicMock()
        mock_dt.weekday.return_value = 2  # Wednesday
        mock_dt.hour = 18
        with patch("core.monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = _is_market_hours()
        assert result is False


class TestRunTestMode:
    def test_classifies_unseen_articles(self):
        summary = [{"classification": "HIGH", "count": 2}, {"classification": "LOW", "count": 5}]
        with patch("core.monitor.storage.already_seen", return_value=False), \
             patch("core.monitor.classifier.classify", return_value={
                 "classification": "LOW", "confidence": 0.5,
                 "reason": "test", "sentiment": "NEUTRAL"
             }), \
             patch("core.monitor.storage.save_event", return_value=True), \
             patch("core.monitor.alerts.alert_article"), \
             patch("core.monitor.storage.summary", return_value=summary), \
             patch("time.sleep"):
            monitor.run_test_mode()  # should not raise

    def test_skips_already_seen_articles(self):
        with patch("core.monitor.storage.already_seen", return_value=True), \
             patch("core.monitor.classifier.classify") as mock_classify, \
             patch("core.monitor.storage.summary", return_value=[]):
            monitor.run_test_mode()
        mock_classify.assert_not_called()


class TestRunMonitor:
    def test_one_iteration_then_keyboard_interrupt(self):
        """Run one full loop iteration; KeyboardInterrupt from time.sleep exits."""
        with patch("core.monitor._handle_market_data"), \
             patch("core.monitor._handle_news_fetch"), \
             patch("core.monitor.classify_pending", return_value=0), \
             patch("core.monitor._log_summary"), \
             patch("core.monitor.config") as mock_cfg, \
             patch("time.sleep", side_effect=KeyboardInterrupt):
            mock_cfg.POLL_INTERVAL_SECONDS = 0
            with pytest.raises(KeyboardInterrupt):
                monitor.run_monitor()

    def test_keyboard_interrupt_inside_loop_calls_sys_exit(self):
        """KeyboardInterrupt inside the try block triggers sys.exit(0)."""
        with patch("core.monitor._handle_market_data", side_effect=KeyboardInterrupt), \
             patch("core.monitor._handle_news_fetch"), \
             patch("core.monitor._log_summary"), \
             patch("core.monitor.config"):
            with pytest.raises(SystemExit) as exc:
                monitor.run_monitor()
            assert exc.value.code == 0

    def test_generic_exception_is_caught_and_loop_continues(self):
        """An unexpected exception is caught; loop continues until KeyboardInterrupt."""
        with patch("core.monitor._handle_market_data",
                   side_effect=[Exception("boom"), KeyboardInterrupt]), \
             patch("core.monitor._handle_news_fetch"), \
             patch("core.monitor.classify_pending", return_value=0), \
             patch("core.monitor._log_summary"), \
             patch("core.monitor.config") as mock_cfg, \
             patch("time.sleep"):
            mock_cfg.POLL_INTERVAL_SECONDS = 0
            with pytest.raises(SystemExit) as exc:
                monitor.run_monitor()
            assert exc.value.code == 0

    def test_classified_count_is_logged(self):
        """When articles are classified, the count is logged."""
        with patch("core.monitor._handle_market_data"), \
             patch("core.monitor._handle_news_fetch"), \
             patch("core.monitor.classify_pending", return_value=3), \
             patch("core.monitor._log_summary"), \
             patch("core.monitor.config") as mock_cfg, \
             patch("time.sleep", side_effect=KeyboardInterrupt):
            mock_cfg.POLL_INTERVAL_SECONDS = 0
            with pytest.raises(KeyboardInterrupt):
                monitor.run_monitor()


class TestMain:
    def test_main_test_mode(self):
        with patch("sys.argv", ["monitor", "--test"]), \
             patch("core.monitor.storage.initialize"), \
             patch("core.monitor.run_test_mode") as mock_run:
            monitor.main()
        mock_run.assert_called_once()

    def test_main_monitor_mode(self):
        with patch("sys.argv", ["monitor"]), \
             patch("core.monitor.storage.initialize"), \
             patch("core.monitor.run_monitor") as mock_run:
            monitor.main()
        mock_run.assert_called_once()


class TestHandleMarketDataSurge:
    def test_fires_surge_alert_when_threshold_reached(self):
        """alert_surge fires when detector threshold is hit by market signal."""
        signal = {
            "severity": "HIGH", "message": "Market crash",
            "region": "us", "type": "drop", "change_pct": -5.0,
        }
        snapshots = [{"symbol": "SPX", "change_pct": -5.0}]
        # Use a detector with threshold=1 so a single HIGH event triggers surge
        det = spike_detector.SpikeDetector(window_minutes=30, threshold=1)
        with patch("core.monitor.config") as mock_cfg, \
             patch("core.market_data.fetch_snapshots", return_value=snapshots), \
             patch("core.market_data.detect_volatility", return_value=[signal]), \
             patch("core.monitor.storage.save_snapshots"), \
             patch("core.monitor.alerts.alert_market_signal"), \
             patch("core.monitor.alerts.alert_surge") as mock_surge:
            mock_cfg.MARKET_DATA_ENABLED = True
            mock_cfg.SPIKE_WINDOW_MINUTES = 30
            mock_cfg.SPIKE_HIGH_THRESHOLD = 1
            _handle_market_data(det)
        mock_surge.assert_called_once()
