"""CLI healthcheck entrypoint for bootstrap status."""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import load_settings
from utils.io import ensure_dir


APP_NAME = "solana-memecoin-signal-engine"


def main() -> int:
    settings = load_settings()
    required_dirs = [
        settings.DATA_DIR,
        settings.RAW_DATA_DIR,
        settings.PROCESSED_DATA_DIR,
        settings.SIGNALS_DIR,
        settings.TRADES_DIR,
        settings.POSITIONS_DIR,
        settings.SMOKE_DIR,
    ]

    for directory in required_dirs:
        ensure_dir(Path(directory))

    payload = {
        "status": "ok",
        "app": APP_NAME,
        "env": settings.APP_ENV,
        "x_validation_enabled": settings.X_VALIDATION_ENABLED,
        "openclaw_local_only": settings.OPENCLAW_LOCAL_ONLY,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
