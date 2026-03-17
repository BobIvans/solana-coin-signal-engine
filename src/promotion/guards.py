from __future__ import annotations

from .cooldowns import is_x_cooldown_active, resolve_degraded_x_policy
from .kill_switch import is_kill_switch_active


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

    pnl_pct_today = float(state.get("counters", {}).get("pnl_pct_today", 0.0))
    if abs(min(pnl_pct_today, 0.0)) >= float(safety.get("max_daily_loss_pct", 999999.0)):
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


def effective_position_scale(signal: dict, state: dict, config: dict) -> float:
    mode = state.get("active_mode")
    scale = float(config.get("modes", {}).get(mode, {}).get("position_size_scale", 1.0))
    if signal.get("x_status") == "degraded":
        policy = resolve_degraded_x_policy(mode, config)
        if policy == "reduced_size":
            return round(scale * 0.5, 4)
        if policy in {"watchlist_only", "pause_new_entries"}:
            return 0.0
    return scale
