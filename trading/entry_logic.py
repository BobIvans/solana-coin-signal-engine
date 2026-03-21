"""Entry decision routing for scored tokens."""

from __future__ import annotations

from typing import Any

from trading.entry_sizing import compute_entry_position_contract
from trading.entry_snapshot import build_entry_snapshot
from trading.regime_rules import decide_regime
from utils.bundle_contract_fields import copy_bundle_contract_fields, copy_linkage_contract_fields
from utils.clock import utc_now_iso
from utils.short_horizon_contract_fields import copy_short_horizon_contract_fields
from utils.wallet_family_contract_fields import copy_wallet_family_contract_fields

_ALLOWED_DECISIONS = {"SCALP", "TREND", "IGNORE"}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _apply_discovery_lag_entry_policy(result: dict[str, Any], token_ctx: dict[str, Any], settings: Any) -> None:
    discovery_status = str(token_ctx.get("discovery_freshness_status") or "").strip().lower()
    discovery_lag_sec = _safe_int(token_ctx.get("discovery_lag_sec"), 0)
    delayed_launch_window_flag = bool(token_ctx.get("delayed_launch_window_flag"))
    trend_block_sec = _safe_int(getattr(settings, "DISCOVERY_LAG_TREND_BLOCK_SEC", getattr(settings, "DISCOVERY_FIRST_WINDOW_SEC", 60)), 60)
    hard_block_enabled = bool(getattr(settings, "DISCOVERY_POST_FIRST_WINDOW_HARD_BLOCK_ENABLED", True))
    hard_block_lag_sec = _safe_int(getattr(settings, "DISCOVERY_POST_FIRST_WINDOW_SCALP_MAX_LAG_SEC", trend_block_sec), trend_block_sec)

    result["discovery_lag_penalty_applied"] = False
    result["discovery_lag_blocked_trend"] = False
    result["discovery_lag_size_multiplier"] = 1.0

    if delayed_launch_window_flag and "discovery_delayed_launch_window" not in result["regime_blockers"]:
        result["regime_blockers"].append("discovery_delayed_launch_window")

    if discovery_status == "post_first_window" and result["entry_decision"] == "TREND":
        result["entry_decision"] = "SCALP"
        result["entry_reason"] = "discovery_lag_blocked_trend"
        result["expected_hold_class"] = "short"
        result["discovery_lag_penalty_applied"] = True
        result["discovery_lag_blocked_trend"] = True
        if "discovery_post_first_window" not in result["regime_blockers"]:
            result["regime_blockers"].append("discovery_post_first_window")
        if "discovery_lag_blocked_trend" not in result["regime_reason_flags"]:
            result["regime_reason_flags"].append("discovery_lag_blocked_trend")

    if discovery_lag_sec > 0 and discovery_lag_sec >= trend_block_sec:
        result["discovery_lag_penalty_applied"] = True
        if "discovery_lag_high" not in result["regime_reason_flags"]:
            result["regime_reason_flags"].append("discovery_lag_high")

    if hard_block_enabled and discovery_status == "post_first_window" and discovery_lag_sec >= hard_block_lag_sec:
        result["entry_decision"] = "IGNORE"
        result["entry_reason"] = "discovery_lag_hard_block"
        result["expected_hold_class"] = "none"
        if "discovery_lag_hard_block" not in result["regime_blockers"]:
            result["regime_blockers"].append("discovery_lag_hard_block")
        if "discovery_lag_hard_block" not in result["entry_warnings"]:
            result["entry_warnings"].append("discovery_lag_hard_block")

    result["regime_reason_flags"] = _dedupe(result["regime_reason_flags"])
    result["regime_blockers"] = _dedupe(result["regime_blockers"])
    result["entry_flags"] = _dedupe([*result["regime_reason_flags"], *result["regime_blockers"]])
    result["entry_warnings"] = _dedupe(result["entry_warnings"])


def decide_entry(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    regime = decide_regime(token_ctx, settings)
    regime_reason_flags = _dedupe(regime.get("regime_reason_flags", []))
    regime_blockers = _dedupe(regime.get("regime_blockers", []))

    result: dict[str, Any] = {
        "token_address": token_ctx.get("token_address"),
        "symbol": token_ctx.get("symbol"),
        "name": token_ctx.get("name"),
        **copy_bundle_contract_fields(token_ctx),
        **copy_linkage_contract_fields(token_ctx),
        **copy_short_horizon_contract_fields(token_ctx),
        **copy_wallet_family_contract_fields(token_ctx),
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

    _apply_discovery_lag_entry_policy(result, token_ctx, settings)

    if result["entry_decision"] not in _ALLOWED_DECISIONS:
        raise ValueError(f"Unhandled entry decision: {result['entry_decision']}")

    result.update(compute_entry_position_contract(token_ctx, result, settings))
    result["entry_snapshot"] = build_entry_snapshot(token_ctx)
    return result


def decide_entries(tokens: list[dict[str, Any]], settings: Any) -> list[dict[str, Any]]:
    return [decide_entry(token, settings) for token in tokens]
