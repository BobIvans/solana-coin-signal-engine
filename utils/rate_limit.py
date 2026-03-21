"""Simple in-memory provider throttling guardrail."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from config.settings import load_settings


@dataclass
class SoftLimiter:
    interval_sec: float
    last_acquired: float = field(default=0.0)

    def remaining_wait(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last_acquired
        return max(self.interval_sec - elapsed, 0.0)

    def acquire(self, *, blocking: bool = True) -> bool:
        wait_sec = self.remaining_wait()
        if wait_sec > 0:
            if not blocking:
                return False
            time.sleep(wait_sec)
        self.last_acquired = time.monotonic()
        return True


_SETTINGS = load_settings()
_INTERVAL = 0.05 if _SETTINGS.GLOBAL_RATE_LIMIT_ENABLED else 0.0

_LIMITERS = {
    "dex": SoftLimiter(interval_sec=_INTERVAL),
    "helius": SoftLimiter(interval_sec=_INTERVAL),
    "x": SoftLimiter(interval_sec=_INTERVAL),
}


def acquire(provider_name: str, *, blocking: bool = True) -> bool:
    limiter = _LIMITERS[provider_name]
    return limiter.acquire(blocking=blocking)
