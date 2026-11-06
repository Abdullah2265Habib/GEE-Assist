"""Download speed over a short sliding window."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable


class SpeedMeter:
    """Bytes per second over the last ``window`` seconds."""

    def __init__(self, window: float = 5.0, clock: Callable[[], float] = time.monotonic):
        self._window = window
        self._clock = clock
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, byte_count: int) -> None:
        self._samples.append((self._clock(), byte_count))
        self._trim()

    def rate(self) -> float:
        self._trim()
        if not self._samples:
            return 0.0
        span = max(self._clock() - self._samples[0][0], 1.0)  # avoid huge rates from one quick sample
        return sum(count for _, count in self._samples) / span

    def reset(self) -> None:
        self._samples.clear()

    def _trim(self) -> None:
        cutoff = self._clock() - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
