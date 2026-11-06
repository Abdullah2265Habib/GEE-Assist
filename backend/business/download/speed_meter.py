"""Download speed of the running download, measured in real time.

GEE sends a chunk as several requests of up to ~43 MB, and each one arrives in
a single burst after several seconds. So the speed is the bytes that arrived
in the last ``window`` seconds divided by that time, rather than the speed of
each burst. It is worked out at the moment it is read, so it falls back
towards zero while nothing arrives instead of keeping the last burst's value.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional

MIN_SPAN = 1.0   # seconds; keeps one early burst from showing as an absurd speed


class SpeedMeter:
    """Bytes per second over the last ``window`` seconds, and the average since ``start``."""

    def __init__(self, window: float = 20.0, clock: Callable[[], float] = time.monotonic):
        self._window = window
        self._clock = clock
        self._samples: deque[tuple[float, int]] = deque()
        self._started: Optional[float] = None
        self._total = 0

    def start(self) -> None:
        """Start measuring a download (again): earlier bytes no longer count."""
        self._samples.clear()
        self._started = self._clock()
        self._total = 0

    def add(self, byte_count: int) -> None:
        if self._started is None:
            self.start()
        self._samples.append((self._clock(), byte_count))
        self._total += byte_count
        self._trim()

    def rate(self) -> float:
        """Bytes per second over the last ``window`` seconds (or since ``start`` if that is shorter)."""
        if self._started is None:
            return 0.0
        self._trim()
        span = min(self._window, self._clock() - self._started)
        return sum(count for _, count in self._samples) / max(span, MIN_SPAN)

    def average(self) -> float:
        """Bytes per second since ``start``."""
        if self._started is None:
            return 0.0
        return self._total / max(self._clock() - self._started, MIN_SPAN)

    def reset(self) -> None:
        self._samples.clear()
        self._started = None
        self._total = 0

    def _trim(self) -> None:
        cutoff = self._clock() - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
