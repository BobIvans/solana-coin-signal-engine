"""Smoke-check bootstrap layer by creating dirs and writing artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, ensure_dir, write_json
from utils.json_contracts import SignalRecord, TradeRecord

APP_NAME = "solana-memecoin-signal-engine"


def main() -> int:
    settings = load_settings()

    dirs = [
        settings.DATA_DIR,
        settings.RAW_DATA_DIR,
        settings.PROCESSED_DATA_DIR,
        settings.SIGNALS_DIR,
        settings.TRADES_DIR,
        settings.POSITIONS_DIR,
        settings.SMOKE_DIR,
    ]
    for directory in dirs:
        ensure_dir(directory)

    now = utc_now_iso()
    signal = SignalRecord(
        token_address="BOOTSTRAP_TEST",
        timestamp_utc=now,
        stage="bootstrap_smoke",
        status="ok",
        payload={"source": "smoke_bootstrap"},
    )
    trade = TradeRecord(
        token_address="BOOTSTRAP_TEST",
        entry_time_utc=now,
        exit_time_utc=utc_now_iso(),
        regime="SMOKE",
        pnl_pct=0.0,
        exit_reason="bootstrap_check",
    )

    append_jsonl(settings.SIGNALS_DIR / "signals.jsonl", signal.to_dict())
    append_jsonl(settings.TRADES_DIR / "trades.jsonl", trade.to_dict())

    status_payload = {
        "status": "ok",
        "timestamp_utc": utc_now_iso(),
        "app": APP_NAME,
        "dirs_created": True,
        "jsonl_write_ok": True,
        "settings_loaded": True,
    }
    write_json(settings.SMOKE_DIR / "bootstrap_status.json", status_payload)
    print(json.dumps(status_payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
