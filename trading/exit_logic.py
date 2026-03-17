"""Exit decision orchestration layer."""

from __future__ import annotations

from typing import Any

from trading.exit_rules import evaluate_hard_exit, evaluate_scalp_exit, evaluate_trend_exit
from trading.exit_snapshot import build_exit_snapshot
from trading.position_monitor import compute_hold_sec, compute_pnl_pct, compute_position_deltas
from utils.clock import utc_now_iso

_ALLOWED_DECISIONS = {"HOLD", "PARTIAL_EXIT", "FULL_EXIT"}
_REQUIRED_CURRENT_FIELDS = {
    "price_usd_now",
    "buy_pressure_now",
    "volume_velocity_now",
    "liquidity_usd_now",
    "x_validation_score_now",
    "x_status_now",
    "bundle_cluster_score_now",
    "dev_sell_pressure_now",
    "rug_flag_now",
}


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _missing_fields(current_ctx: dict[str, Any]) -> list[str]:
    return sorted([field for field in _REQUIRED_CURRENT_FIELDS if field not in current_ctx or current_ctx.get(field) is None])


def decide_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    now_ts = str(current_ctx.get("now_ts") or current_ctx.get("observed_at") or utc_now_iso())
    hold_sec = compute_hold_sec(str(position_ctx.get("entry_time") or now_ts), now_ts)

    current_price = float(current_ctx.get("price_usd_now", current_ctx.get("price_usd") or 0.0))
    entry_price = float(position_ctx.get("entry_price_usd") or 0.0)
    pnl_pct = compute_pnl_pct(entry_price, current_price)

    deltas = compute_position_deltas(dict(position_ctx.get("entry_snapshot") or {}), current_ctx)
    current_eval_ctx = {
        **current_ctx,
        "hold_sec": hold_sec,
        "pnl_pct": pnl_pct,
        **deltas,
    }

    warnings: list[str] = []
    missing = _missing_fields(current_ctx)
    if missing:
        warnings.append("missing_current_state_fields")
        if bool(settings.EXIT_ENGINE_FAILCLOSED):
            decision = {
                "exit_decision": "FULL_EXIT",
                "exit_fraction": 1.0,
                "exit_reason": "missing_current_state_failclosed",
                "exit_flags": ["failclosed_missing_fields"],
                "exit_warnings": warnings,
                "exit_status": "partial",
            }
            return _finalize(position_ctx, current_eval_ctx, settings, decision, hold_sec, pnl_pct, now_ts)

    hard = evaluate_hard_exit(position_ctx, current_eval_ctx, settings)
    if hard["exit_decision"] == "HOLD":
        regime = str(position_ctx.get("entry_decision") or "").upper()
        if regime == "SCALP":
            decision = evaluate_scalp_exit(position_ctx, current_eval_ctx, settings)
        elif regime == "TREND":
            decision = evaluate_trend_exit(position_ctx, current_eval_ctx, settings)
        else:
            decision = {
                "exit_decision": "HOLD",
                "exit_fraction": 0.0,
                "exit_reason": "hold_conditions_intact",
                "exit_flags": [],
                "exit_warnings": ["unknown_entry_decision"],
            }
    else:
        decision = hard

    wallet_features = current_ctx.get("wallet_features") or {}
    netflow_bias = float(wallet_features.get("smart_wallet_netflow_bias") or 0.0)
    tier1_distribution = int(wallet_features.get("smart_wallet_tier1_distribution_hits") or 0)
    if netflow_bias < 0:
        decision.setdefault("exit_warnings", []).append("smart_wallet_netflow_reversal")
    if tier1_distribution > 0:
        decision.setdefault("exit_warnings", []).append("tier1_wallet_distribution_detected")

    decision["exit_warnings"] = _dedupe([*decision.get("exit_warnings", []), *warnings])
    return _finalize(position_ctx, current_eval_ctx, settings, decision, hold_sec, pnl_pct, now_ts)


def _finalize(position_ctx: dict, current_ctx: dict, settings: Any, decision: dict, hold_sec: int, pnl_pct: float, now_ts: str) -> dict:
    result = {
        "position_id": position_ctx.get("position_id"),
        "token_address": position_ctx.get("token_address"),
        "symbol": position_ctx.get("symbol"),
        "exit_decision": decision.get("exit_decision"),
        "exit_fraction": float(decision.get("exit_fraction", 0.0)),
        "exit_reason": str(decision.get("exit_reason") or "hold_conditions_intact"),
        "hold_sec": hold_sec,
        "pnl_pct": round(pnl_pct, 4),
        "exit_flags": _dedupe(list(decision.get("exit_flags", []))),
        "exit_warnings": _dedupe(list(decision.get("exit_warnings", []))),
        "exit_snapshot": build_exit_snapshot(position_ctx, current_ctx),
        "exit_status": decision.get("exit_status", "ok"),
        "decided_at": now_ts,
        "contract_version": settings.EXIT_CONTRACT_VERSION,
    }
    if result["exit_decision"] not in _ALLOWED_DECISIONS:
        raise ValueError(f"Unhandled exit_decision: {result['exit_decision']}")
    return result


def decide_exits(positions: list[dict], current_states: list[dict], settings: Any) -> list[dict]:
    state_map = {str(item.get("token_address") or ""): item for item in current_states}
    decisions: list[dict] = []
    for position in positions:
        if position.get("is_open") is False:
            continue
        token_address = str(position.get("token_address") or "")
        current_ctx = dict(state_map.get(token_address) or {})
        current_ctx.setdefault("token_address", token_address)
        decisions.append(decide_exit(position, current_ctx, settings))
    return decisions
