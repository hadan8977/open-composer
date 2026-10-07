"""Shared sliding-window limiter: Alpaca allows 200 calls/minute for orders and market data
together, so every broker and data call takes a slot here and waits when the window is full."""

from __future__ import annotations

import time as _time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        per_minute: int = 180,
        *,
        clock: Callable[[], float] = _time.monotonic,
        sleep: Callable[[float], None] = _time.sleep,
    ):
        if per_minute < 1:
            raise ValueError("per_minute must be >= 1")
        self.per_minute = per_minute
        self._clock, self._sleep = clock, sleep
        self._stamps: deque[float] = deque()
        self.calls = 0
        self.waited_seconds = 0.0

    def acquire(self, n: int = 1) -> None:
        n = min(max(n, 1), self.per_minute)
        while True:
            now = self._clock()
            while self._stamps and now - self._stamps[0] >= 60.0:
                self._stamps.popleft()
            if len(self._stamps) + n <= self.per_minute:
                self._stamps.extend([now] * n)
                self.calls += n
                return
            wait = 60.0 - (now - self._stamps[0]) + 0.01
            self.waited_seconds += wait
            self._sleep(wait)
