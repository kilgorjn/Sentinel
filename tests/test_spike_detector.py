"""Tests for core/spike_detector.py — SpikeDetector sliding window logic."""

import pytest
from datetime import datetime, timedelta, timezone

from core.spike_detector import SpikeDetector


def _article(title="Fed Cuts Rates", published_at=None):
    return {
        "title": title,
        "published_at": published_at or datetime.now(timezone.utc),
    }


class TestRecordAndCount:
    def test_starts_at_zero(self):
        det = SpikeDetector(window_minutes=30, threshold=3)
        assert det.current_count() == 0

    def test_high_event_increments_count(self):
        det = SpikeDetector(window_minutes=30, threshold=3)
        det.record(_article(), "HIGH")
        assert det.current_count() == 1

    def test_non_high_event_does_not_increment(self):
        det = SpikeDetector(window_minutes=30, threshold=3)
        det.record(_article(), "MEDIUM")
        det.record(_article(), "LOW")
        assert det.current_count() == 0

    def test_multiple_high_events_accumulate(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        for i in range(3):
            det.record(_article(f"Headline {i}"), "HIGH")
        assert det.current_count() == 3


class TestSurgeDetection:
    def test_surge_fires_at_threshold(self):
        det = SpikeDetector(window_minutes=30, threshold=3)
        det.record(_article("A"), "HIGH")
        det.record(_article("B"), "HIGH")
        result = det.record(_article("C"), "HIGH")
        assert result is True

    def test_surge_returns_false_before_threshold(self):
        det = SpikeDetector(window_minutes=30, threshold=3)
        r1 = det.record(_article("A"), "HIGH")
        r2 = det.record(_article("B"), "HIGH")
        assert r1 is False
        assert r2 is False

    def test_surge_fires_only_once(self):
        det = SpikeDetector(window_minutes=30, threshold=2)
        det.record(_article("A"), "HIGH")
        det.record(_article("B"), "HIGH")  # surge fires
        result = det.record(_article("C"), "HIGH")  # already surging
        assert result is False

    def test_is_surge_reflects_state(self):
        det = SpikeDetector(window_minutes=30, threshold=2)
        assert det.is_surge() is False
        det.record(_article("A"), "HIGH")
        det.record(_article("B"), "HIGH")
        assert det.is_surge() is True


class TestWindowEviction:
    def test_old_events_are_evicted(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        # Inject an event 60 minutes ago — outside the 30-min window
        old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        det.record(_article(published_at=old_time), "HIGH")
        # current_count() evicts stale entries
        assert det.current_count() == 0

    def test_recent_events_are_kept(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        det.record(_article(published_at=recent), "HIGH")
        assert det.current_count() == 1

    def test_surge_clears_when_count_drops(self):
        det = SpikeDetector(window_minutes=1, threshold=2)
        # Add events timestamped in the past so they'll be evicted
        old = datetime.now(timezone.utc) - timedelta(minutes=2)
        det.record(_article("A", published_at=old), "HIGH")
        det.record(_article("B", published_at=old), "HIGH")
        # Force surge state manually by setting threshold met
        det._surge_active = True

        # New record call evicts the old events — surge should clear
        det.record(_article("C"), "MEDIUM")
        assert det.is_surge() is False

    def test_naive_published_at_treated_as_utc(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        naive = datetime.now(timezone.utc).replace(tzinfo=None)
        det.record(_article(published_at=naive), "HIGH")
        assert det.current_count() == 1


class TestRecentEvents:
    def test_recent_events_returns_titles(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        det.record(_article("Headline Alpha"), "HIGH")
        det.record(_article("Headline Beta"), "HIGH")
        titles = det.recent_events()
        assert "Headline Alpha" in titles
        assert "Headline Beta" in titles

    def test_recent_events_excludes_old(self):
        det = SpikeDetector(window_minutes=30, threshold=5)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        det.record(_article("Old News", published_at=old), "HIGH")
        assert det.recent_events() == []
