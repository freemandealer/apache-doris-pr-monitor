from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """A minimal thread-safe TTL cache."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < now:
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=expires_at)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
