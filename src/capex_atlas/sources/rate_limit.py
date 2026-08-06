"""Client-side rate limiting.

SEC has historically throttled automated access above ten requests per second.
The default here is well under that: the package is a research tool, nobody is
waiting on latency, and being a good citizen of a free public API costs nothing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

DEFAULT_REQUESTS_PER_SECOND = 2.5


class TokenBucket:
    """Thread-safe token bucket.

    Takes ``monotonic`` and ``sleep`` as parameters so tests can drive time
    directly instead of actually waiting.
    """

    def __init__(
        self,
        rate_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        burst: int = 1,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self._rate = rate_per_second
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._monotonic = monotonic
        self._sleep = sleep
        self._updated = monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a token is available. Returns the seconds waited."""
        with self._lock:
            waited = 0.0
            while True:
                now = self._monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) * self._rate
                )
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return waited
                shortfall = (1 - self._tokens) / self._rate
                self._sleep(shortfall)
                waited += shortfall
