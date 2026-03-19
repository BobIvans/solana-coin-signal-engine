"""Entry decision routing for scored tokens."""

from __future__ import annotations

from typing import Any

from trading.entry_sizing import compute_entry_confidence, compute_recommended_position_pct
from trading.entry_snapshot import build_entry_snapshot
from trading.regime_rules import is_scalp_candidate, is_trend_candidate, should_ignore
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
    ignore = should_ignore(token_ctx, settings)
    flags = list(ignore.get("flags", []))
    warnings = list(ignore.get("warnings", []))

    decision = "IGNORE"
    reason = ignore.get("reason") or "insufficient_momentum"

    trend = is_trend_candidate(token_ctx, settings)
    scalp = is_scalp_candidate(token_ctx, settings)

    if not ignore.get("ignore"):
        if trend["eligible"]:
            decision = "TREND"
            reason = trend["reason"]
            flags.extend(trend.get("flags", []))
            warnings.extend(trend.get("warnings", []))
        elif scalp["eligible"]:
            decision = "SCALP"
            reason = scalp["reason"]
            flags.extend(scalp.get("flags", []))
            warnings.extend(scalp.get("warnings", []))
        else:
            decision = "IGNORE"
            reason = "insufficient_social_confirmation" if "smart_wallet_hits_too_low" in trend.get("failures", []) else "insufficient_momentum"
            if str(token_ctx.get("x_status") or "").lower() == "degraded":
                warnings.append("x_status_degraded")

    result: dict[str, Any] = {
        "token_address": token_ctx.get("token_address"),
        "symbol": token_ctx.get("symbol"),
        "name": token_ctx.get("name"),
        **copy_bundle_contract_fields(token_ctx),
        **copy_short_horizon_contract_fields(token_ctx),
        "entry_decision": decision,
        "entry_reason": reason,
        "entry_flags": _dedupe(flags),
        "entry_warnings": _dedupe(warnings),
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
