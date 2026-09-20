"""
Simple thread-safe TTL cache.

Used to avoid re-querying SQLite for the same hot endpoint within a
short window. Data only changes once per trading day, so a 60-second
TTL is more than enough for development and safe for early production.

Not a replacement for a real cache (Redis, memcached). Not persistent.
Cleared on process restart.
"""
from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    """In-memory key → (expires_at, value) store with thread safety."""

    def __init__(self, default_ttl: float = 60.0) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            expires = time.monotonic() + (self._default_ttl if ttl is None else ttl)
            self._store[key] = (expires, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove every key starting with `prefix`. Returns count removed."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)


# Module-level singleton — routes import via get_cache().
_cache = TTLCache(default_ttl=60.0)


def get_cache() -> TTLCache:
    return _cache
