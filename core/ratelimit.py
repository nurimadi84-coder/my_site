"""Ограничение частоты запросов в памяти процесса (скользящее окно по ключу, обычно IP)."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _fresh(self, key: str, now: float) -> list[float]:
        for other in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[other]
        stamps = [ts for ts in self._hits.get(key, []) if now - ts < self.window]
        self._hits[key] = stamps
        return stamps

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._fresh(key, time.time())) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.time()
            self._fresh(key, now).append(now)

    def allow(self, key: str) -> bool:
        """Учесть запрос и вернуть False, если лимит уже исчерпан."""
        with self._lock:
            now = time.time()
            stamps = self._fresh(key, now)
            if len(stamps) >= self.limit:
                return False
            stamps.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        with self._lock:
            stamps = self._fresh(key, time.time())
            if not stamps:
                return 0
            return max(1, int(self.window - (time.time() - stamps[0])) + 1)
