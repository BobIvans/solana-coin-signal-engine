"""Exit decision orchestration layer."""

from __future__ import annotations

from typing import Any

from src.promotion.kill_switch import is_kill_switch_active
from trading.exit_rules import evaluate_hard_exit, evaluate_scalp_exit, evaluate_trend_exit
from trading.exit_snapshot import build_exit_snapshot
from trading.position_monitor import compute_hold_sec, compute_pnl_pct, compute_position_deltas
from utils.clock import utc_now_iso

_ALLOWED_DECISIONS = {"HOLD", "PARTIAL_EXIT", "FULL_EXIT"}
_CRITICAL_CURRENT_FIELDS = {
    "price_usd_now",
}
_DEGRADABLE_CURRENT_FIELDS = {
    "buy_pressure_now",
    "volume_velocity_now",
    "liquidity_usd_now",
    "x_validation_score_now",
    "x_status_now",
    "bundle_cluster_score_now",
    "dev_sell_pressure_now",
    "rug_flag_now",
}
_FIELD_FALLBACKS = {
    "price_usd_now": [("current", "price_usd_now"), ("current", "price_usd")],
    "buy_pressure_now": [("current", "buy_pressure_now"), ("current", "buy_pressure"), ("entry", "buy_pressure")],
    "volume_velocity_now": [("current", "volume_velocity_now"), ("current", "volume_velocity"), ("entry", "volume_velocity")],
    "liquidity_usd_now": [("current", "liquidity_usd_now"), ("current", "liquidity_usd"), ("entry", "liquidity_usd")],
    "x_validation_score_now": [("current", "x_validation_score_now"), ("current", "x_validation_score"), ("entry", "x_validation_score")],
    "x_status_now": [("current", "x_status_now"), ("current", "x_status"), ("entry", "x_status")],
    "bundle_cluster_score_now": [("current", "bundle_cluster_score_now"), ("current", "bundle_cluster_score"), ("entry", "bundle_cluster_score")],
    "dev_sell_pressure_now": [("current", "dev_sell_pressure_now"), ("current", "dev_sell_pressure_5m"), ("entry", "dev_sell_pressure_5m")],
    "rug_flag_now": [("current", "rug_flag_now"), ("current", "rug_flag"), ("entry", "rug_flag")],
}


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _hydrate_current_state(position_ctx: dict[str, Any], current_ctx: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    hydrated_ctx = dict(current_ctx)
    entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})
    fallback_applied_fields: list[str] = []
    missing_critical_fields: list[str] = []
    missing_degradable_fields: list[str] = []

    for field, fallbacks in _FIELD_FALLBACKS.items():
        resolved = False
        for idx, (source, key) in enumerate(fallbacks):
            source_ctx = current_ctx if source == "current" else entry_snapshot
            if key in source_ctx and source_ctx.get(key) is not None:
                hydrated_ctx[field] = source_ctx.get(key)
                if idx > 0:
                    fallback_applied_fields.append(field)
                resolved = True
                break
        if resolved:
            continue
        if field in _CRITICAL_CURRENT_FIELDS:
            missing_critical_fields.append(field)
        else:
            missing_degradable_fields.append(field)

    resolution = {
        "missing_critical_fields": sorted(missing_critical_fields),
        "missing_degradable_fields": sorted(missing_degradable_fields),
        "fallback_applied_fields": sorted(set(fallback_applied_fields)),
    }
    resolution["degraded_current_state"] = bool(
        resolution["fallback_applied_fields"] or resolution["missing_degradable_fields"]
    )
    return hydrated_ctx, resolution


def _kill_switch_config_from_settings(settings: Any) -> dict[str, dict[str, str]]:
    configured_path = getattr(settings, "KILL_SWITCH_FILE", None) or getattr(settings, "kill_switch_file", None)
    return {"safety": {"kill_switch_file": str(configured_path or "runs/runtime/kill_switch.flag")}}


def _resolve_kill_switch_active(settings: Any) -> bool:
    return is_kill_switch_active(_kill_switch_config_from_settings(settings))


def decide_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    hydrated_ctx, resolution = _hydrate_current_state(position_ctx, current_ctx)
    now_ts = str(hydrated_ctx.get("now_ts") or hydrated_ctx.get("observed_at") or utc_now_iso())
    hold_sec = compute_hold_sec(str(position_ctx.get("entry_time") or now_ts), now_ts)

    current_price = float(hydrated_ctx.get("price_usd_now", hydrated_ctx.get("price_usd") or 0.0))
    entry_price = float(position_ctx.get("entry_price_usd") or 0.0)
    pnl_pct = compute_pnl_pct(entry_price, current_price)

    deltas = compute_position_deltas(dict(position_ctx.get("entry_snapshot") or {}), hydrated_ctx)
    kill_switch_config = _kill_switch_config_from_settings(settings)
    current_eval_ctx = {
        **hydrated_ctx,
        "hold_sec": hold_sec,
        "pnl_pct": pnl_pct,
        "kill_switch_active": _resolve_kill_switch_active(settings),
        "kill_switch_file": kill_switch_config["safety"]["kill_switch_file"],
        **deltas,
    }

    if current_eval_ctx["kill_switch_active"]:
        decision = evaluate_hard_exit(position_ctx, current_eval_ctx, settings)
        return _finalize(position_ctx, current_eval_ctx, settings, decision, hold_sec, pnl_pct, now_ts)

    warnings: list[str] = []
    if resolution["degraded_current_state"]:
        warnings.append("degraded_current_state_fields")
    warnings.extend([f"fallback_{field}" for field in resolution["fallback_applied_fields"]])
    warnings.extend([f"missing_degradable_{field}" for field in resolution["missing_degradable_fields"]])

    if resolution["missing_critical_fields"]:
        warnings.extend([f"missing_critical_{field}" for field in resolution["missing_critical_fields"]])
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

    wallet_features = hydrated_ctx.get("wallet_features") or {}
    netflow_bias = float(wallet_features.get("smart_wallet_netflow_bias") or 0.0)
    tier1_distribution = int(wallet_features.get("smart_wallet_tier1_distribution_hits") or 0)
    if netflow_bias < 0:
        decision.setdefault("exit_warnings", []).append("smart_wallet_netflow_reversal")
    if tier1_distribution > 0:
        decision.setdefault("exit_warnings", []).append("tier1_wallet_distribution_detected")

    decision["exit_warnings"] = _dedupe([*decision.get("exit_warnings", []), *warnings])
    if resolution["degraded_current_state"]:
        decision["exit_status"] = "partial"
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
