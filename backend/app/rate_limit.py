"""In-memory sliding-window rate limiter for expensive AI endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max(1, max_requests)
        self._window_seconds = max(1, window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        if self._max_requests <= 0:
            return True, 0

        now = time.monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self._max_requests:
                retry_after = max(1, int(self._window_seconds - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            return True, 0


def client_ip(forwarded_for: str | None, direct_host: str | None) -> str:
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"
    return direct_host or "unknown"
