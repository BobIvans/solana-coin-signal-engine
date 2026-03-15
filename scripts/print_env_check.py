"""Print non-secret bootstrap configuration for quick inspection."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


if __name__ == "__main__":
    settings = load_settings()
    payload = {
        "env": settings.APP_ENV,
        "data_dirs": {
            "data": str(settings.DATA_DIR),
            "raw": str(settings.RAW_DATA_DIR),
            "processed": str(settings.PROCESSED_DATA_DIR),
            "signals": str(settings.SIGNALS_DIR),
            "trades": str(settings.TRADES_DIR),
            "positions": str(settings.POSITIONS_DIR),
            "smoke": str(settings.SMOKE_DIR),
        },
        "x_flags": {
            "x_validation_enabled": settings.X_VALIDATION_ENABLED,
            "x_degraded_mode_allowed": settings.X_DEGRADED_MODE_ALLOWED,
            "x_max_tokens_per_cycle": settings.X_MAX_TOKENS_PER_CYCLE,
        },
        "cache_ttl": {
            "x_cache_ttl_sec": settings.X_CACHE_TTL_SEC,
            "dex_cache_ttl_sec": settings.DEX_CACHE_TTL_SEC,
            "helius_cache_ttl_sec": settings.HELIUS_CACHE_TTL_SEC,
        },
        "concurrency_limits": {
            "x_max_concurrency": settings.X_MAX_CONCURRENCY,
            "global_rate_limit_enabled": settings.GLOBAL_RATE_LIMIT_ENABLED,
        },
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
