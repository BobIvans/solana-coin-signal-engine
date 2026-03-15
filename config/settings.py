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

    ONCHAIN_ENRICHMENT_ENABLED: bool
    ONCHAIN_ENRICHMENT_MAX_TOKENS: int
    ONCHAIN_ENRICHMENT_FAILOPEN: bool
    HELIUS_API_KEY: str
    HELIUS_TX_ADDR_LIMIT: int
    HELIUS_TX_SIG_BATCH: int
    HELIUS_ENRICH_CACHE_TTL_SEC: int
    SOLANA_RPC_URL: str
    SOLANA_RPC_COMMITMENT: str
    SMART_WALLET_SEED_PATH: Path
    SMART_WALLET_HIT_WINDOW_SEC: int
    PROGRAM_ID_MAP_PATH: Path
    ALLOW_LAUNCH_PATH_HEURISTICS_ONLY: bool

    RUG_ENGINE_ENABLED: bool
    RUG_ENGINE_FAILCLOSED: bool
    RUG_ENGINE_PARTIAL_ALLOWED: bool
    RUG_IGNORE_THRESHOLD: float
    RUG_WATCH_THRESHOLD: float
    RUG_TOP1_HOLDER_HARD_MAX: float
    RUG_TOP20_HOLDER_HARD_MAX: float
    RUG_DEV_SELL_PRESSURE_WARN: float
    RUG_DEV_SELL_PRESSURE_HARD: float
    RUG_REQUIRE_DISTINCT_BURN_AND_LOCK: bool
    RUG_LP_BURN_OWNER_ALLOWLIST: str
    RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH: Path
    RUG_EVENT_CACHE_TTL_SEC: int

    # Unified scoring (PR-6)
    UNIFIED_SCORING_ENABLED: bool
    UNIFIED_SCORING_FAILOPEN: bool
    UNIFIED_SCORING_REQUIRE_X: bool
    UNIFIED_SCORE_ENTRY_THRESHOLD: float
    UNIFIED_SCORE_WATCH_THRESHOLD: float
    UNIFIED_SCORE_IGNORE_RUG_THRESHOLD: float
    UNIFIED_SCORE_X_DEGRADED_PENALTY: float
    UNIFIED_SCORE_PARTIAL_DATA_PENALTY: float
    UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR: float
    UNIFIED_SCORE_CONTRACT_VERSION: str

    # Entry selector (PR-7)
    ENTRY_SELECTOR_ENABLED: bool
    ENTRY_SELECTOR_FAILCLOSED: bool
    ENTRY_SCALP_SCORE_MIN: float
    ENTRY_TREND_SCORE_MIN: float
    ENTRY_SCALP_MAX_AGE_SEC: int
    ENTRY_SCALP_MAX_HOLD_SEC: int
    ENTRY_TREND_MIN_X_SCORE: float
    ENTRY_SCALP_MIN_X_SCORE: float
    ENTRY_RUG_MAX_SCALP: float
    ENTRY_RUG_MAX_TREND: float
    ENTRY_BUY_PRESSURE_MIN_SCALP: float
    ENTRY_BUY_PRESSURE_MIN_TREND: float
    ENTRY_FIRST30S_BUY_RATIO_MIN: float
    ENTRY_BUNDLE_CLUSTER_MIN: float
    ENTRY_SMART_WALLET_HITS_MIN_TREND: int
    ENTRY_HOLDER_GROWTH_MIN_TREND: int
    ENTRY_DEGRADED_X_SIZE_MULTIPLIER: float
    ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER: float
    ENTRY_MAX_BASE_POSITION_PCT: float
    ENTRY_CONTRACT_VERSION: str

    # Paper trader (PR-9)
    PAPER_TRADER_ENABLED: bool
    PAPER_TRADER_FAILCLOSED: bool
    PAPER_STARTING_CAPITAL_SOL: float
    PAPER_MAX_CONCURRENT_POSITIONS: int
    PAPER_ALLOW_PARTIAL_EXITS: bool
    PAPER_DEFAULT_SLIPPAGE_BPS: float
    PAPER_MAX_SLIPPAGE_BPS: float
    PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY: float
    PAPER_PRIORITY_FEE_BASE_SOL: float
    PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER: float
    PAPER_FAILED_TX_BASE_PROB: float
    PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON: float
    PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON: float
    PAPER_PARTIAL_FILL_ALLOWED: bool
    PAPER_PARTIAL_FILL_MIN_RATIO: float
    PAPER_MARK_TO_MARKET_INTERVAL_SEC: int
    PAPER_APPEND_ONLY_LOGS: bool
    PAPER_CONTRACT_VERSION: str


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
    return merged.get(key, default)


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


def _as_unit_float(raw_value: Any, *, key: str) -> float:
    value = float(raw_value)
    if value < 0 or value > 1:
        raise ValueError(f"{key} must be between 0 and 1")
    return value




def _as_positive_float(raw_value: Any, *, key: str) -> float:
    value = float(raw_value)
    if value <= 0:
        raise ValueError(f"{key} must be > 0")
    return value


def _as_non_negative_float(raw_value: Any, *, key: str) -> float:
    value = float(raw_value)
    if value < 0:
        raise ValueError(f"{key} must be >= 0")
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
        ONCHAIN_ENRICHMENT_ENABLED=_as_bool(_get_env(merged, "ONCHAIN_ENRICHMENT_ENABLED", "true"), key="ONCHAIN_ENRICHMENT_ENABLED"),
        ONCHAIN_ENRICHMENT_MAX_TOKENS=_as_positive_int(_get_env(merged, "ONCHAIN_ENRICHMENT_MAX_TOKENS", "5"), key="ONCHAIN_ENRICHMENT_MAX_TOKENS"),
        ONCHAIN_ENRICHMENT_FAILOPEN=_as_bool(_get_env(merged, "ONCHAIN_ENRICHMENT_FAILOPEN", "true"), key="ONCHAIN_ENRICHMENT_FAILOPEN"),
        HELIUS_API_KEY=str(_get_env(merged, "HELIUS_API_KEY", "")),
        HELIUS_TX_ADDR_LIMIT=_as_positive_int(_get_env(merged, "HELIUS_TX_ADDR_LIMIT", "40"), key="HELIUS_TX_ADDR_LIMIT"),
        HELIUS_TX_SIG_BATCH=_as_positive_int(_get_env(merged, "HELIUS_TX_SIG_BATCH", "25"), key="HELIUS_TX_SIG_BATCH"),
        HELIUS_ENRICH_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "HELIUS_ENRICH_CACHE_TTL_SEC", "300"), key="HELIUS_ENRICH_CACHE_TTL_SEC"),
        SOLANA_RPC_URL=str(_get_env(merged, "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")),
        SOLANA_RPC_COMMITMENT=str(_get_env(merged, "SOLANA_RPC_COMMITMENT", "confirmed")),
        SMART_WALLET_SEED_PATH=_as_abs_path(_get_env(merged, "SMART_WALLET_SEED_PATH", "data/seeds/smart_wallets.json")),
        SMART_WALLET_HIT_WINDOW_SEC=_as_positive_int(_get_env(merged, "SMART_WALLET_HIT_WINDOW_SEC", "300"), key="SMART_WALLET_HIT_WINDOW_SEC"),
        PROGRAM_ID_MAP_PATH=_as_abs_path(_get_env(merged, "PROGRAM_ID_MAP_PATH", "config/program_ids.json")),
        ALLOW_LAUNCH_PATH_HEURISTICS_ONLY=_as_bool(_get_env(merged, "ALLOW_LAUNCH_PATH_HEURISTICS_ONLY", "true"), key="ALLOW_LAUNCH_PATH_HEURISTICS_ONLY"),
        RUG_ENGINE_ENABLED=_as_bool(_get_env(merged, "RUG_ENGINE_ENABLED", "true"), key="RUG_ENGINE_ENABLED"),
        RUG_ENGINE_FAILCLOSED=_as_bool(_get_env(merged, "RUG_ENGINE_FAILCLOSED", "true"), key="RUG_ENGINE_FAILCLOSED"),
        RUG_ENGINE_PARTIAL_ALLOWED=_as_bool(_get_env(merged, "RUG_ENGINE_PARTIAL_ALLOWED", "true"), key="RUG_ENGINE_PARTIAL_ALLOWED"),
        RUG_IGNORE_THRESHOLD=_as_unit_float(_get_env(merged, "RUG_IGNORE_THRESHOLD", "0.55"), key="RUG_IGNORE_THRESHOLD"),
        RUG_WATCH_THRESHOLD=_as_unit_float(_get_env(merged, "RUG_WATCH_THRESHOLD", "0.35"), key="RUG_WATCH_THRESHOLD"),
        RUG_TOP1_HOLDER_HARD_MAX=_as_unit_float(_get_env(merged, "RUG_TOP1_HOLDER_HARD_MAX", "0.20"), key="RUG_TOP1_HOLDER_HARD_MAX"),
        RUG_TOP20_HOLDER_HARD_MAX=_as_unit_float(_get_env(merged, "RUG_TOP20_HOLDER_HARD_MAX", "0.65"), key="RUG_TOP20_HOLDER_HARD_MAX"),
        RUG_DEV_SELL_PRESSURE_WARN=_as_unit_float(_get_env(merged, "RUG_DEV_SELL_PRESSURE_WARN", "0.10"), key="RUG_DEV_SELL_PRESSURE_WARN"),
        RUG_DEV_SELL_PRESSURE_HARD=_as_unit_float(_get_env(merged, "RUG_DEV_SELL_PRESSURE_HARD", "0.25"), key="RUG_DEV_SELL_PRESSURE_HARD"),
        RUG_REQUIRE_DISTINCT_BURN_AND_LOCK=_as_bool(_get_env(merged, "RUG_REQUIRE_DISTINCT_BURN_AND_LOCK", "true"), key="RUG_REQUIRE_DISTINCT_BURN_AND_LOCK"),
        RUG_LP_BURN_OWNER_ALLOWLIST=str(_get_env(merged, "RUG_LP_BURN_OWNER_ALLOWLIST", "11111111111111111111111111111111")),
        RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH=_as_abs_path(_get_env(merged, "RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH", "config/lock_programs.json")),
        RUG_EVENT_CACHE_TTL_SEC=_as_positive_int(_get_env(merged, "RUG_EVENT_CACHE_TTL_SEC", "300"), key="RUG_EVENT_CACHE_TTL_SEC"),

        UNIFIED_SCORING_ENABLED=_as_bool(_get_env(merged, "UNIFIED_SCORING_ENABLED", "true"), key="UNIFIED_SCORING_ENABLED"),
        UNIFIED_SCORING_FAILOPEN=_as_bool(_get_env(merged, "UNIFIED_SCORING_FAILOPEN", "false"), key="UNIFIED_SCORING_FAILOPEN"),
        UNIFIED_SCORING_REQUIRE_X=_as_bool(_get_env(merged, "UNIFIED_SCORING_REQUIRE_X", "false"), key="UNIFIED_SCORING_REQUIRE_X"),
        UNIFIED_SCORE_ENTRY_THRESHOLD=float(_get_env(merged, "UNIFIED_SCORE_ENTRY_THRESHOLD", "82")),
        UNIFIED_SCORE_WATCH_THRESHOLD=float(_get_env(merged, "UNIFIED_SCORE_WATCH_THRESHOLD", "68")),
        UNIFIED_SCORE_IGNORE_RUG_THRESHOLD=_as_unit_float(_get_env(merged, "UNIFIED_SCORE_IGNORE_RUG_THRESHOLD", "0.55"), key="UNIFIED_SCORE_IGNORE_RUG_THRESHOLD"),
        UNIFIED_SCORE_X_DEGRADED_PENALTY=float(_get_env(merged, "UNIFIED_SCORE_X_DEGRADED_PENALTY", "8")),
        UNIFIED_SCORE_PARTIAL_DATA_PENALTY=float(_get_env(merged, "UNIFIED_SCORE_PARTIAL_DATA_PENALTY", "5")),
        UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR=_as_unit_float(_get_env(merged, "UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR", "0.50"), key="UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR"),
        UNIFIED_SCORE_CONTRACT_VERSION=str(_get_env(merged, "UNIFIED_SCORE_CONTRACT_VERSION", "unified_score_v1")),
        ENTRY_SELECTOR_ENABLED=_as_bool(_get_env(merged, "ENTRY_SELECTOR_ENABLED", "true"), key="ENTRY_SELECTOR_ENABLED"),
        ENTRY_SELECTOR_FAILCLOSED=_as_bool(_get_env(merged, "ENTRY_SELECTOR_FAILCLOSED", "true"), key="ENTRY_SELECTOR_FAILCLOSED"),
        ENTRY_SCALP_SCORE_MIN=float(_get_env(merged, "ENTRY_SCALP_SCORE_MIN", "82")),
        ENTRY_TREND_SCORE_MIN=float(_get_env(merged, "ENTRY_TREND_SCORE_MIN", "86")),
        ENTRY_SCALP_MAX_AGE_SEC=_as_positive_int(_get_env(merged, "ENTRY_SCALP_MAX_AGE_SEC", "480"), key="ENTRY_SCALP_MAX_AGE_SEC"),
        ENTRY_SCALP_MAX_HOLD_SEC=_as_positive_int(_get_env(merged, "ENTRY_SCALP_MAX_HOLD_SEC", "120"), key="ENTRY_SCALP_MAX_HOLD_SEC"),
        ENTRY_TREND_MIN_X_SCORE=float(_get_env(merged, "ENTRY_TREND_MIN_X_SCORE", "65")),
        ENTRY_SCALP_MIN_X_SCORE=float(_get_env(merged, "ENTRY_SCALP_MIN_X_SCORE", "50")),
        ENTRY_RUG_MAX_SCALP=_as_unit_float(_get_env(merged, "ENTRY_RUG_MAX_SCALP", "0.30"), key="ENTRY_RUG_MAX_SCALP"),
        ENTRY_RUG_MAX_TREND=_as_unit_float(_get_env(merged, "ENTRY_RUG_MAX_TREND", "0.20"), key="ENTRY_RUG_MAX_TREND"),
        ENTRY_BUY_PRESSURE_MIN_SCALP=_as_unit_float(_get_env(merged, "ENTRY_BUY_PRESSURE_MIN_SCALP", "0.75"), key="ENTRY_BUY_PRESSURE_MIN_SCALP"),
        ENTRY_BUY_PRESSURE_MIN_TREND=_as_unit_float(_get_env(merged, "ENTRY_BUY_PRESSURE_MIN_TREND", "0.65"), key="ENTRY_BUY_PRESSURE_MIN_TREND"),
        ENTRY_FIRST30S_BUY_RATIO_MIN=_as_unit_float(_get_env(merged, "ENTRY_FIRST30S_BUY_RATIO_MIN", "0.65"), key="ENTRY_FIRST30S_BUY_RATIO_MIN"),
        ENTRY_BUNDLE_CLUSTER_MIN=_as_unit_float(_get_env(merged, "ENTRY_BUNDLE_CLUSTER_MIN", "0.55"), key="ENTRY_BUNDLE_CLUSTER_MIN"),
        ENTRY_SMART_WALLET_HITS_MIN_TREND=_as_positive_int(_get_env(merged, "ENTRY_SMART_WALLET_HITS_MIN_TREND", "2"), key="ENTRY_SMART_WALLET_HITS_MIN_TREND"),
        ENTRY_HOLDER_GROWTH_MIN_TREND=_as_positive_int(_get_env(merged, "ENTRY_HOLDER_GROWTH_MIN_TREND", "20"), key="ENTRY_HOLDER_GROWTH_MIN_TREND"),
        ENTRY_DEGRADED_X_SIZE_MULTIPLIER=_as_unit_float(_get_env(merged, "ENTRY_DEGRADED_X_SIZE_MULTIPLIER", "0.50"), key="ENTRY_DEGRADED_X_SIZE_MULTIPLIER"),
        ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER=_as_unit_float(_get_env(merged, "ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER", "0.60"), key="ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER"),
        ENTRY_MAX_BASE_POSITION_PCT=_as_unit_float(_get_env(merged, "ENTRY_MAX_BASE_POSITION_PCT", "1.00"), key="ENTRY_MAX_BASE_POSITION_PCT"),
        ENTRY_CONTRACT_VERSION=str(_get_env(merged, "ENTRY_CONTRACT_VERSION", "entry_selector_v1")),
        PAPER_TRADER_ENABLED=_as_bool(_get_env(merged, "PAPER_TRADER_ENABLED", "true"), key="PAPER_TRADER_ENABLED"),
        PAPER_TRADER_FAILCLOSED=_as_bool(_get_env(merged, "PAPER_TRADER_FAILCLOSED", "true"), key="PAPER_TRADER_FAILCLOSED"),
        PAPER_STARTING_CAPITAL_SOL=_as_positive_float(_get_env(merged, "PAPER_STARTING_CAPITAL_SOL", "0.1"), key="PAPER_STARTING_CAPITAL_SOL"),
        PAPER_MAX_CONCURRENT_POSITIONS=_as_positive_int(_get_env(merged, "PAPER_MAX_CONCURRENT_POSITIONS", "3"), key="PAPER_MAX_CONCURRENT_POSITIONS"),
        PAPER_ALLOW_PARTIAL_EXITS=_as_bool(_get_env(merged, "PAPER_ALLOW_PARTIAL_EXITS", "true"), key="PAPER_ALLOW_PARTIAL_EXITS"),
        PAPER_DEFAULT_SLIPPAGE_BPS=_as_non_negative_float(_get_env(merged, "PAPER_DEFAULT_SLIPPAGE_BPS", "150"), key="PAPER_DEFAULT_SLIPPAGE_BPS"),
        PAPER_MAX_SLIPPAGE_BPS=_as_positive_float(_get_env(merged, "PAPER_MAX_SLIPPAGE_BPS", "1200"), key="PAPER_MAX_SLIPPAGE_BPS"),
        PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY=_as_non_negative_float(_get_env(merged, "PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY", "1.0"), key="PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY"),
        PAPER_PRIORITY_FEE_BASE_SOL=_as_non_negative_float(_get_env(merged, "PAPER_PRIORITY_FEE_BASE_SOL", "0.00002"), key="PAPER_PRIORITY_FEE_BASE_SOL"),
        PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER=_as_positive_float(_get_env(merged, "PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER", "1.75"), key="PAPER_PRIORITY_FEE_SPIKE_MULTIPLIER"),
        PAPER_FAILED_TX_BASE_PROB=_as_unit_float(_get_env(merged, "PAPER_FAILED_TX_BASE_PROB", "0.03"), key="PAPER_FAILED_TX_BASE_PROB"),
        PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON=_as_unit_float(_get_env(merged, "PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON", "0.05"), key="PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON"),
        PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON=_as_unit_float(_get_env(merged, "PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON", "0.04"), key="PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON"),
        PAPER_PARTIAL_FILL_ALLOWED=_as_bool(_get_env(merged, "PAPER_PARTIAL_FILL_ALLOWED", "true"), key="PAPER_PARTIAL_FILL_ALLOWED"),
        PAPER_PARTIAL_FILL_MIN_RATIO=_as_unit_float(_get_env(merged, "PAPER_PARTIAL_FILL_MIN_RATIO", "0.50"), key="PAPER_PARTIAL_FILL_MIN_RATIO"),
        PAPER_MARK_TO_MARKET_INTERVAL_SEC=_as_positive_int(_get_env(merged, "PAPER_MARK_TO_MARKET_INTERVAL_SEC", "5"), key="PAPER_MARK_TO_MARKET_INTERVAL_SEC"),
        PAPER_APPEND_ONLY_LOGS=_as_bool(_get_env(merged, "PAPER_APPEND_ONLY_LOGS", "true"), key="PAPER_APPEND_ONLY_LOGS"),
        PAPER_CONTRACT_VERSION=str(_get_env(merged, "PAPER_CONTRACT_VERSION", "paper_trader_v1")),
    )
