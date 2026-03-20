"""Minimal JSON-like structured logger with UTC timestamps."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _UtcJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp_utc": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        extra_fields = getattr(record, "fields", {})
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("solana-memecoin-signal-engine")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_UtcJsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


_LOGGER = _build_logger()


def log_info(event: str, **fields: Any) -> None:
    _LOGGER.info(event, extra={"fields": fields})


def log_warning(event: str, **fields: Any) -> None:
    _LOGGER.warning(event, extra={"fields": fields})


def log_error(event: str, **fields: Any) -> None:
    _LOGGER.error(event, extra={"fields": fields})
