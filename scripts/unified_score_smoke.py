"""Smoke runner for the current unified scoring architecture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import load_settings
from scoring.unified_score import score_token, score_tokens
from utils.io import write_json


def _base_token() -> dict:
    return {
        "mint": "smoke_mint_1",
        "token_id": "smoke_mint_1",
        "token_address": "smoke_mint_1",
        "symbol": "SMOKE",
        "x_score": 80,
        "liquidity_usd": 50000,
        "buy_pressure": 0.70,
        "holder_growth_5m": 20,
        "rug_status": "pass",
        "wallet_registry_status": "validated",
        "smart_wallet_score_sum": 12.0,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_tier2_hits": 0,
        "smart_wallet_tier3_hits": 0,
        "smart_wallet_early_entry_hits": 1,
        "smart_wallet_active_hits": 1,
        "smart_wallet_watch_hits": 0,
        "smart_wallet_conviction_bonus": 1.0,
        "smart_wallet_registry_confidence": "high",
        "timestamp": "2026-03-20T00:00:00Z",
    }


def _validate_mode(record: dict, mode: str) -> None:
    required = {
        "final_score_pre_wallet",
        "final_score",
        "wallet_score_component_raw",
        "wallet_score_component_applied",
        "wallet_weighting_mode",
        "wallet_weighting_effective_mode",
    }
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(f"{mode}: missing score fields {missing}")
    if record["wallet_weighting_mode"] != mode:
        raise ValueError(f"{mode}: unexpected wallet_weighting_mode {record['wallet_weighting_mode']}")
    if mode == "off":
        if record["final_score"] != record["final_score_pre_wallet"]:
            raise ValueError("off: final_score must equal final_score_pre_wallet")
        if record["wallet_score_component_applied"] != 0.0:
            raise ValueError("off: wallet_score_component_applied must be zero")
    elif mode == "shadow":
        if record["final_score"] != record["final_score_pre_wallet"]:
            raise ValueError("shadow: final_score must equal final_score_pre_wallet")
        if record["wallet_score_component_raw"] <= 0.0:
            raise ValueError("shadow: wallet_score_component_raw must be positive")
        if record["wallet_score_component_applied"] != 0.0:
            raise ValueError("shadow: wallet_score_component_applied must stay zero")
    elif mode == "on":
        expected = round(float(record["final_score_pre_wallet"]) + float(record["wallet_score_component_applied"]), 6)
        if round(float(record["final_score"]), 6) != expected:
            raise ValueError("on: final_score must equal pre-wallet plus applied wallet component")
        if record["wallet_score_component_applied"] <= 0.0:
            raise ValueError("on: wallet_score_component_applied must be positive")


def run() -> dict:
    settings = load_settings()
    token = _base_token()

    off = score_token(token, wallet_weighting_mode="off")
    shadow = score_token(token, wallet_weighting_mode="shadow")
    on = score_token(token, wallet_weighting_mode="on")

    for mode, record in (("off", off), ("shadow", shadow), ("on", on)):
        _validate_mode(record, mode)

    batch_scored, batch_events = score_tokens(
        shortlist=[token],
        x_validated=[],
        enriched=[],
        rug_assessed=[],
        wallet_weighting_mode="shadow",
    )
    if len(batch_scored) != 1 or len(batch_events) != 1:
        raise ValueError("batch scoring smoke must emit one scored token and one event row")

    summary = {
        "off": {
            "final_score_pre_wallet": off["final_score_pre_wallet"],
            "final_score": off["final_score"],
            "wallet_score_component_applied": off["wallet_score_component_applied"],
        },
        "shadow": {
            "final_score_pre_wallet": shadow["final_score_pre_wallet"],
            "final_score": shadow["final_score"],
            "wallet_score_component_raw": shadow["wallet_score_component_raw"],
            "wallet_score_component_applied": shadow["wallet_score_component_applied"],
        },
        "on": {
            "final_score_pre_wallet": on["final_score_pre_wallet"],
            "final_score": on["final_score"],
            "wallet_score_component_applied": on["wallet_score_component_applied"],
        },
        "batch_event_count": len(batch_events),
        "batch_event_wallet_mode": batch_events[0]["wallet_weighting_mode"],
    }
    out_path = settings.SMOKE_DIR / "unified_score_smoke_summary.json"
    write_json(out_path, summary)
    summary["summary_path"] = str(out_path)
    return summary


def main() -> int:
    print(json.dumps(run(), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
