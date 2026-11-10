"""Per-source rate limiting.

Public OSINT sources publish limits and enforce them by blocking you. We treat
those limits as part of the collector contract rather than an afterthought: a
collector that cannot be called politely does not get registered.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimit:
    """At most ``requests`` calls per ``per_seconds`` seconds."""

    requests: int
    per_seconds: float

    def __post_init__(self) -> None:
        if self.requests < 1:
            raise ValueError("requests must be >= 1")
        if self.per_seconds <= 0:
            raise ValueError("per_seconds must be > 0")


class RateLimiter:
    """Sliding-window limiter, one window per source, shared across threads."""

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, source: str, limit: RateLimit) -> float:
        """Block until a slot is free. Returns the seconds actually waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                window = self._windows.setdefault(source, deque())
                cutoff = now - limit.per_seconds
                while window and window[0] <= cutoff:
                    window.popleft()

                if len(window) < limit.requests:
                    window.append(now)
                    return waited

                sleep_for = window[0] + limit.per_seconds - now

            sleep_for = max(sleep_for, 0.01)
            time.sleep(sleep_for)
            waited += sleep_for

    def reset(self, source: str | None = None) -> None:
        with self._lock:
            if source is None:
                self._windows.clear()
            else:
                self._windows.pop(source, None)
