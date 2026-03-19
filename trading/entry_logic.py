"""Entry decision routing for scored tokens."""

from __future__ import annotations

from typing import Any

from trading.entry_sizing import compute_entry_confidence, compute_recommended_position_pct
from trading.entry_snapshot import build_entry_snapshot
from trading.regime_rules import decide_regime
from utils.bundle_contract_fields import copy_bundle_contract_fields
from utils.clock import utc_now_iso
from utils.short_horizon_contract_fields import copy_short_horizon_contract_fields

_ALLOWED_DECISIONS = {"SCALP", "TREND", "IGNORE"}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def decide_entry(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    regime = decide_regime(token_ctx, settings)
    regime_reason_flags = _dedupe(regime.get("regime_reason_flags", []))
    regime_blockers = _dedupe(regime.get("regime_blockers", []))

    result: dict[str, Any] = {
        "token_address": token_ctx.get("token_address"),
        "symbol": token_ctx.get("symbol"),
        "name": token_ctx.get("name"),
        **copy_bundle_contract_fields(token_ctx),
        **copy_short_horizon_contract_fields(token_ctx),
        "entry_decision": regime["regime_decision"],
        "entry_reason": regime["reason"],
        "entry_flags": _dedupe([*regime_reason_flags, *regime_blockers]),
        "entry_warnings": _dedupe(regime.get("warnings", [])),
        "regime_confidence": float(regime.get("regime_confidence") or 0.0),
        "regime_reason_flags": regime_reason_flags,
        "regime_blockers": regime_blockers,
        "expected_hold_class": regime.get("expected_hold_class") or "none",
        "entry_status": "ok",
        "decided_at": utc_now_iso(),
        "contract_version": settings.ENTRY_CONTRACT_VERSION,
    }

    if result["entry_decision"] not in _ALLOWED_DECISIONS:
        raise ValueError(f"Unhandled entry decision: {result['entry_decision']}")

    result["entry_confidence"] = compute_entry_confidence(token_ctx, result, settings)
    result["recommended_position_pct"] = compute_recommended_position_pct(token_ctx, result, settings)
    result["entry_snapshot"] = build_entry_snapshot(token_ctx)

    if result["entry_decision"] == "IGNORE":
        result["recommended_position_pct"] = 0.0

    return result


def decide_entries(tokens: list[dict[str, Any]], settings: Any) -> list[dict[str, Any]]:
    return [decide_entry(token, settings) for token in tokens]
