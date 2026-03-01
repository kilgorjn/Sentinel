"""
Sliding-window spike detector for HIGH-impact news events.

Mirrors the login volume spike pattern: maintain a rolling time window,
count qualifying events, and fire a SURGE alert when the count crosses
a threshold — giving ops teams advance warning before brokerage login
volume climbs.
"""

from collections import deque
from datetime import datetime, timedelta, timezone
import logging

import config

log = logging.getLogger(__name__)


class SpikeDetector:
    """
    Tracks HIGH-classification events in a sliding time window.

    When the count crosses SPIKE_HIGH_THRESHOLD within SPIKE_WINDOW_MINUTES,
    a surge is detected (analogous to a login-volume spike).
    """

    def __init__(
        self,
        window_minutes: int = config.SPIKE_WINDOW_MINUTES,
        threshold: int = config.SPIKE_HIGH_THRESHOLD,
    ):
        self.window = timedelta(minutes=window_minutes)
        self.threshold = threshold
        # Deque of (timestamp, title) for HIGH events in the window
        self._events: deque[tuple[datetime, str]] = deque()
        self._surge_active = False

    def _evict_old(self, now: datetime) -> None:
        """Remove events outside the current sliding window."""
        cutoff = now - self.window
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def record(self, article: dict, classification: str) -> bool:
        """
        Record an article's classification result.
        Returns True if a NEW surge is detected this call.
        """
        now = datetime.now(timezone.utc)
        self._evict_old(now)

        if classification == "HIGH":
            self._events.append((now, article.get("title", "")))

        count = len(self._events)
        log.debug("HIGH events in last %d min: %d / %d", self.window.seconds // 60, count, self.threshold)

        if count >= self.threshold and not self._surge_active:
            self._surge_active = True
            log.warning("SURGE detected: %d HIGH events in %d min window", count, self.window.seconds // 60)
            return True

        if count < self.threshold and self._surge_active:
            self._surge_active = False
            log.info("Surge cleared: HIGH event count dropped to %d", count)

        return False

    def current_count(self) -> int:
        """Return number of HIGH events currently in the window."""
        self._evict_old(datetime.now(timezone.utc))
        return len(self._events)

    def is_surge(self) -> bool:
        return self._surge_active

    def recent_events(self) -> list[str]:
        """Titles of HIGH events currently in the window."""
        self._evict_old(datetime.now(timezone.utc))
        return [title for _, title in self._events]
