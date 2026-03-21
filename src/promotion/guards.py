from __future__ import annotations

from analytics.evidence_weighted_sizing import compute_evidence_weighted_size

from .cooldowns import is_x_cooldown_active, resolve_degraded_x_policy
from .kill_switch import is_kill_switch_active


def _daily_loss_pct(state: dict) -> float:
    counters = state.get("counters", {})
    realized_pnl_sol_today = float(counters.get("realized_pnl_sol_today", 0.0) or 0.0)
    starting_capital_sol = float(counters.get("starting_capital_sol", state.get("starting_capital_sol", 0.0)) or 0.0)
    if starting_capital_sol > 0:
        return abs(min(realized_pnl_sol_today / starting_capital_sol * 100.0, 0.0))
    pnl_pct_today = float(counters.get("pnl_pct_today", 0.0) or 0.0)
    return abs(min(pnl_pct_today, 0.0))


def evaluate_entry_guards(signal: dict, state: dict, config: dict) -> dict:
    mode = state.get("active_mode")
    mode_cfg = config.get("modes", {}).get(mode, {})
    safety = config.get("safety", {})

    hard_block_reasons: list[str] = []
    soft_reasons: list[str] = []

    if is_kill_switch_active(config):
        hard_block_reasons.append("kill_switch_active")
    if mode == "paused":
        hard_block_reasons.append("mode_paused")
    if not mode_cfg.get("open_positions", False):
        hard_block_reasons.append("mode_no_open_positions")

    max_open = int(mode_cfg.get("max_open_positions", 999999))
    if len(state.get("open_positions", [])) >= max_open:
        hard_block_reasons.append("max_open_positions_reached")

    trades_today = int(state.get("counters", {}).get("trades_today", 0))
    max_trades = int(mode_cfg.get("max_trades_per_day", 999999))
    if trades_today >= max_trades:
        hard_block_reasons.append("max_trades_per_day_reached")

    daily_loss_pct = _daily_loss_pct(state)
    if daily_loss_pct >= float(safety.get("max_daily_loss_pct", 999999.0)):
        hard_block_reasons.append("max_daily_loss_pct_breached")

    if int(state.get("consecutive_losses", 0)) >= int(safety.get("max_consecutive_losses", 999999)):
        hard_block_reasons.append("max_consecutive_losses_breached")

    allowed = [r.upper() for r in mode_cfg.get("allow_regimes", ["SCALP", "TREND"])]
    regime = str(signal.get("regime", "SCALP")).upper()
    if regime not in allowed:
        hard_block_reasons.append("regime_not_allowed")

    if is_x_cooldown_active(state):
        policy = resolve_degraded_x_policy(mode, config)
        if mode in {"constrained_paper", "expanded_paper"} and policy in {"watchlist_only", "pause_new_entries"}:
            hard_block_reasons.append("x_cooldown_policy_block")
        else:
            soft_reasons.append("x_cooldown_reduced")

    if signal.get("x_status") == "degraded":
        soft_reasons.append("x_status_degraded")

    if state.get("force_watchlist_only"):
        hard_block_reasons.append("watchlist_forced")

    return {
        "hard_block": len(hard_block_reasons) > 0,
        "hard_block_reasons": hard_block_reasons,
        "soft_reasons": soft_reasons,
    }


def should_block_entry(guard_results: dict) -> bool:
    return bool(guard_results.get("hard_block"))


def _base_policy_position_scale_details(signal: dict, state: dict, config: dict) -> dict:
    mode = state.get("active_mode")
    mode_scale = float(config.get("modes", {}).get(mode, {}).get("position_size_scale", 1.0))
    scale = mode_scale
    origin = "mode_policy_only"
    reason_codes: list[str] = []

    if signal.get("x_status") == "degraded":
        policy = resolve_degraded_x_policy(mode, config)
        if policy == "reduced_size":
            scale = round(mode_scale * 0.5, 4)
            origin = "degraded_x_policy"
            reason_codes.append("x_status_degraded_size_reduced")
        elif policy in {"watchlist_only", "pause_new_entries"}:
            scale = 0.0
            origin = "degraded_x_policy"
            reason_codes.append("x_status_degraded_entry_blocked")

    return {
        "mode_position_scale": round(mode_scale, 4),
        "effective_position_scale": round(scale, 4),
        "policy_origin": origin,
        "policy_reason_codes": reason_codes,
    }


def effective_position_scale(signal: dict, state: dict, config: dict) -> float:
    return _base_policy_position_scale_details(signal, state, config)["effective_position_scale"]


def compute_position_sizing(signal: dict, state: dict, config: dict) -> dict:
    policy_details = _base_policy_position_scale_details(signal, state, config)
    recommended_position_pct = float(signal.get("recommended_position_pct", 0.0) or 0.0)
    base_position_pct = round(max(0.0, min(1.0, recommended_position_pct * policy_details["effective_position_scale"])), 4)
    sizing = compute_evidence_weighted_size(
        signal,
        base_position_pct=base_position_pct,
        config=config,
        policy_origin=policy_details["policy_origin"],
        policy_reason_codes=policy_details["policy_reason_codes"],
    )
    effective_position_pct = float(sizing["effective_position_pct"])
    final_scale = 0.0 if recommended_position_pct <= 0 else round(effective_position_pct / recommended_position_pct, 4)
    return {
        **policy_details,
        **sizing,
        "recommended_position_pct": round(recommended_position_pct, 4),
        "effective_position_scale": final_scale,
    }
