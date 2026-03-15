"""Heuristic launch-path estimator based on parsed enhanced transactions."""

from __future__ import annotations

from typing import Any


PUMPFUN_HINTS = ("pumpfun", "pump.fun")
RAYDIUM_HINTS = ("raydium", "amm")


def _event_text(tx: dict[str, Any]) -> str:
    parts = [
        str(tx.get("type") or ""),
        str(tx.get("source") or ""),
        str(tx.get("description") or ""),
        str(tx.get("programName") or ""),
    ]
    return " ".join(parts).lower()


def estimate_launch_path(token_ctx: dict, txs: list[dict]) -> dict[str, Any]:
    del token_ctx
    first_pumpfun_ts = None
    first_raydium_ts = None

    for tx in txs:
        text = _event_text(tx)
        ts = int(tx.get("timestamp") or tx.get("blockTime") or 0)
        if ts <= 0:
            continue
        if first_pumpfun_ts is None and any(h in text for h in PUMPFUN_HINTS):
            first_pumpfun_ts = ts
        if first_raydium_ts is None and any(h in text for h in RAYDIUM_HINTS):
            first_raydium_ts = ts

    if first_pumpfun_ts and first_raydium_ts and first_raydium_ts >= first_pumpfun_ts:
        return {
            "launch_path_label": "pumpfun_to_raydium_est",
            "pumpfun_to_raydium_sec": first_raydium_ts - first_pumpfun_ts,
            "launch_path_confidence_score": 0.68,
        }

    if first_raydium_ts:
        return {
            "launch_path_label": "raydium_direct_est",
            "pumpfun_to_raydium_sec": None,
            "launch_path_confidence_score": 0.55,
        }

    return {
        "launch_path_label": "unknown",
        "pumpfun_to_raydium_sec": None,
        "launch_path_confidence_score": 0.2,
    }
