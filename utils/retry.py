"""Retry helpers with exponential backoff for network calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def is_retryable_error(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, ConnectionError))


def with_retry(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    max_attempts = int(kwargs.pop("max_attempts", 3))
    base_delay = float(kwargs.pop("base_delay", 0.2))
    sleep_fn = kwargs.pop("sleep_fn", time.sleep)
    blocking = bool(kwargs.pop("blocking", True))

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if not is_retryable_error(exc) or attempt >= max_attempts:
                raise
            sleep_sec = min(base_delay * (2 ** (attempt - 1)), 8.0)
            if blocking:
                sleep_fn(sleep_sec)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry wrapper failed without executing function")
