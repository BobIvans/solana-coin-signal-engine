"""Centralized environment settings for bootstrap infrastructure."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


@dataclass(frozen=True)
class Settings:
    APP_ENV: str
    LOG_LEVEL: str

    DATA_DIR: Path
    RAW_DATA_DIR: Path
    PROCESSED_DATA_DIR: Path
    SIGNALS_DIR: Path
    TRADES_DIR: Path
    POSITIONS_DIR: Path
    SMOKE_DIR: Path

    OPENCLAW_ENABLED: bool
    OPENCLAW_LOCAL_ONLY: bool
    OPENCLAW_PROFILE_PATH: Path
    OPENCLAW_SNAPSHOTS_DIR: Path

    X_VALIDATION_ENABLED: bool
    X_DEGRADED_MODE_ALLOWED: bool
    X_SEARCH_TEST_QUERY: str
    X_MAX_TOKENS_PER_CYCLE: int
    X_MAX_CONCURRENCY: int
    X_CACHE_TTL_SEC: int

    LOCAL_OPENCLAW_ONLY: bool
    OPENCLAW_BROWSER_PROFILE: str
    OPENCLAW_BROWSER_TARGET: str
    OPENCLAW_X_QUERY_MAX: int
    OPENCLAW_X_TOKEN_MAX_CONCURRENCY: int
    OPENCLAW_X_CACHE_TTL_SEC: int
    OPENCLAW_X_PAGE_TIMEOUT_MS: int
    OPENCLAW_X_NAV_TIMEOUT_MS: int
    OPENCLAW_X_MAX_SCROLLS: int
    OPENCLAW_X_MAX_POSTS_PER_QUERY: int
    OPENCLAW_X_DEGRADED_SCORE: int
    OPENCLAW_X_FAILOPEN: bool
    X_VALIDATION_CONTRACT_VERSION: str

    DEX_CACHE_TTL_SEC: int
    HELIUS_CACHE_TTL_SEC: int

    GLOBAL_RATE_LIMIT_ENABLED: bool
    SMART_WALLETS_PATH: Path


def _read_dotenv(dotenv_path: str = ".env") -> dict[str, str]:
    path = Path(dotenv_path)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _get_env(merged: dict[str, Any], key: str, default: Any = None) -> Any:
    value = merged.get(key, default)
    return value


def _as_bool(raw_value: Any, *, key: str) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        raise ValueError(f"Missing required bool: {key}")
    value = str(raw_value).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean for {key}: {raw_value}")


def _as_positive_int(raw_value: Any, *, key: str) -> int:
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{key} must be > 0")
    return value


def _as_abs_path(raw_value: Any) -> Path:
    return Path(str(raw_value)).expanduser().resolve()


def load_settings() -> Settings:
    merged: dict[str, Any] = {**_read_dotenv(), **os.environ}

    log_level = str(_get_env(merged, "LOG_LEVEL", "INFO")).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("LOG_LEVEL must be one of DEBUG/INFO/WARNING/ERROR")

    return Settings(
        APP_ENV=str(_get_env(merged, "APP_ENV", "dev")),
        LOG_LEVEL=log_level,
        DATA_DIR=_as_abs_path(_get_env(merged, "DATA_DIR", "./data")),
        RAW_DATA_DIR=_as_abs_path(_get_env(merged, "RAW_DATA_DIR", "./data/raw")),
        PROCESSED_DATA_DIR=_as_abs_path(_get_env(merged, "PROCESSED_DATA_DIR", "./data/processed")),
        SIGNALS_DIR=_as_abs_path(_get_env(merged, "SIGNALS_DIR", "./data/signals")),
        TRADES_DIR=_as_abs_path(_get_env(merged, "TRADES_DIR", "./data/trades")),
        POSITIONS_DIR=_as_abs_path(_get_env(merged, "POSITIONS_DIR", "./data/positions")),
        SMOKE_DIR=_as_abs_path(_get_env(merged, "SMOKE_DIR", "./data/smoke")),
        OPENCLAW_ENABLED=_as_bool(_get_env(merged, "OPENCLAW_ENABLED", "true"), key="OPENCLAW_ENABLED"),
        OPENCLAW_LOCAL_ONLY=_as_bool(_get_env(merged, "OPENCLAW_LOCAL_ONLY", "true"), key="OPENCLAW_LOCAL_ONLY"),
        OPENCLAW_PROFILE_PATH=_as_abs_path(_get_env(merged, "OPENCLAW_PROFILE_PATH", "~/.openclaw/x-profile")),
        OPENCLAW_SNAPSHOTS_DIR=_as_abs_path(_get_env(merged, "OPENCLAW_SNAPSHOTS_DIR", "./data/smoke")),
        X_VALIDATION_ENABLED=_as_bool(_get_env(merged, "X_VALIDATION_ENABLED", "true"), key="X_VALIDATION_ENABLED"),
        X_DEGRADED_MODE_ALLOWED=_as_bool(_get_env(merged, "X_DEGRADED_MODE_ALLOWED", "true"), key="X_DEGRADED_MODE_ALLOWED"),
        X_SEARCH_TEST_QUERY=str(_get_env(merged, "X_SEARCH_TEST_QUERY", "solana memecoin")),
        X_MAX_TOKENS_PER_CYCLE=_as_positive_int(_get_env(merged, "X_MAX_TOKENS_PER_CYCLE", "5"), key="X_MAX_TOKENS_PER_CYCLE"),
        X_MAX_CONCURRENCY=_as_positive_int(_get_env(merged, "X_MAX_CONCURRENCY", "2"), key="X_MAX_CONCURRENCY"),
        X_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "X_CACHE_TTL_SEC", "600"), key="X_CACHE_TTL_SEC"),
        LOCAL_OPENCLAW_ONLY=_as_bool(_get_env(merged, "LOCAL_OPENCLAW_ONLY", "true"), key="LOCAL_OPENCLAW_ONLY"),
        OPENCLAW_BROWSER_PROFILE=str(_get_env(merged, "OPENCLAW_BROWSER_PROFILE", "openclaw")),
        OPENCLAW_BROWSER_TARGET=str(_get_env(merged, "OPENCLAW_BROWSER_TARGET", "host")),
        OPENCLAW_X_QUERY_MAX=_as_positive_int(_get_env(merged, "OPENCLAW_X_QUERY_MAX", "4"), key="OPENCLAW_X_QUERY_MAX"),
        OPENCLAW_X_TOKEN_MAX_CONCURRENCY=_as_positive_int(_get_env(merged, "OPENCLAW_X_TOKEN_MAX_CONCURRENCY", "2"), key="OPENCLAW_X_TOKEN_MAX_CONCURRENCY"),
        OPENCLAW_X_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "OPENCLAW_X_CACHE_TTL_SEC", "600"), key="OPENCLAW_X_CACHE_TTL_SEC"),
        OPENCLAW_X_PAGE_TIMEOUT_MS=_as_positive_int(_get_env(merged, "OPENCLAW_X_PAGE_TIMEOUT_MS", "12000"), key="OPENCLAW_X_PAGE_TIMEOUT_MS"),
        OPENCLAW_X_NAV_TIMEOUT_MS=_as_positive_int(_get_env(merged, "OPENCLAW_X_NAV_TIMEOUT_MS", "15000"), key="OPENCLAW_X_NAV_TIMEOUT_MS"),
        OPENCLAW_X_MAX_SCROLLS=_as_positive_int(_get_env(merged, "OPENCLAW_X_MAX_SCROLLS", "2"), key="OPENCLAW_X_MAX_SCROLLS"),
        OPENCLAW_X_MAX_POSTS_PER_QUERY=_as_positive_int(_get_env(merged, "OPENCLAW_X_MAX_POSTS_PER_QUERY", "15"), key="OPENCLAW_X_MAX_POSTS_PER_QUERY"),
        OPENCLAW_X_DEGRADED_SCORE=_as_positive_int(_get_env(merged, "OPENCLAW_X_DEGRADED_SCORE", "45"), key="OPENCLAW_X_DEGRADED_SCORE"),
        OPENCLAW_X_FAILOPEN=_as_bool(_get_env(merged, "OPENCLAW_X_FAILOPEN", "true"), key="OPENCLAW_X_FAILOPEN"),
        X_VALIDATION_CONTRACT_VERSION=str(_get_env(merged, "X_VALIDATION_CONTRACT_VERSION", "x_validation_v1")),
        DEX_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "DEX_CACHE_TTL_SEC", "60"), key="DEX_CACHE_TTL_SEC"),
        HELIUS_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "HELIUS_CACHE_TTL_SEC", "120"), key="HELIUS_CACHE_TTL_SEC"),
        GLOBAL_RATE_LIMIT_ENABLED=_as_bool(_get_env(merged, "GLOBAL_RATE_LIMIT_ENABLED", "true"), key="GLOBAL_RATE_LIMIT_ENABLED"),
        SMART_WALLETS_PATH=_as_abs_path(_get_env(merged, "SMART_WALLETS_PATH", "./data/processed/smart_wallets.json")),
    )
