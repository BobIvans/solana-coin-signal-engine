"""Global in-memory cache skeleton for providers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config.settings import load_settings


@dataclass
class SimpleTTLCache:
    ttl: int
    maxsize: int = 1024
    _store: dict[str, tuple[float, Any]] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        if len(self._store) >= self.maxsize:
            oldest = next(iter(self._store))
            self._store.pop(oldest, None)
        resolved_ttl = self.ttl if ttl is None else max(int(ttl), 0)
        self._store[key] = (time.time() + resolved_ttl, value)

    def __len__(self) -> int:
        self._cleanup()
        return len(self._store)

    def _cleanup(self) -> None:
        now = time.time()
        expired = [key for key, (expires_at, _) in self._store.items() if expires_at < now]
        for key in expired:
            self._store.pop(key, None)


_SETTINGS = load_settings()
_CACHES: dict[str, SimpleTTLCache] = {
    "dex": SimpleTTLCache(ttl=_SETTINGS.DEX_CACHE_TTL_SEC),
    "helius": SimpleTTLCache(ttl=_SETTINGS.HELIUS_CACHE_TTL_SEC),
    "x": SimpleTTLCache(ttl=_SETTINGS.OPENCLAW_X_CACHE_TTL_SEC),
}


def cache_get(cache_name: str, key: str) -> Any:
    return _CACHES[cache_name].get(key)


def cache_set(cache_name: str, key: str, value: Any, *, ttl_sec: int | None = None) -> None:
    _CACHES[cache_name].set(key, value, ttl=ttl_sec)


def cache_stats() -> dict[str, dict[str, int]]:
    return {name: {"size": len(cache), "maxsize": cache.maxsize} for name, cache in _CACHES.items()}


dex_cache = _CACHES["dex"]
helius_cache = _CACHES["helius"]
x_cache = _CACHES["x"]
