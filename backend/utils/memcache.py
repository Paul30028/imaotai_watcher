"""Tiny thread-safe in-process TTL cache.

This replaces the Redis-backed caching the project used to need when the
API and scheduler were separate processes/containers. Now that the
scheduler runs as a background thread inside the same API process (see
main.py's lifespan), a plain in-memory cache shared by both is simpler and
removes an external dependency -- it just doesn't survive a process
restart, which is fine for data that's re-fetchable (app version, today's
session/shop catalogue) or short-lived (an SMS rate-limit window).
"""
from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at < time.time():
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None


cache = TTLCache()
