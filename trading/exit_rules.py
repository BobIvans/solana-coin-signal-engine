"""Rule evaluators for deterministic exit decisions."""

from __future__ import annotations

from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _partial_taken(position_ctx: dict[str, Any], idx: int) -> bool:
    explicit = bool(position_ctx.get(f"partial_{idx}_taken"))
    partials_taken = position_ctx.get("partials_taken") or []
    if isinstance(partials_taken, list):
        if idx in partials_taken:
            return True
        if f"partial_{idx}" in partials_taken:
            return True
    return explicit


def _hold(reason: str = "hold_conditions_intact", *, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "exit_decision": "HOLD",
        "exit_fraction": 0.0,
        "exit_reason": reason,
        "exit_flags": [],
        "exit_warnings": warnings or [],
    }


def _full(reason: str, flags: list[str]) -> dict[str, Any]:
    return {
        "exit_decision": "FULL_EXIT",
        "exit_fraction": 1.0,
        "exit_reason": reason,
        "exit_flags": flags,
        "exit_warnings": [],
    }


def evaluate_hard_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    dev_sell = _to_float(current_ctx.get("dev_sell_pressure_now", current_ctx.get("dev_sell_pressure_5m")))
    if bool(settings.EXIT_DEV_SELL_HARD) and dev_sell > 0:
        return _full("dev_sell_detected", ["dev_sell_detected"])

    if bool(settings.EXIT_RUG_FLAG_HARD) and bool(current_ctx.get("rug_flag_now")):
        return _full("rug_flag_triggered", ["rug_flag_detected"])

    return _hold()


def evaluate_scalp_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    hold_sec = int(current_ctx.get("hold_sec", 0))
    pnl_pct = _to_float(current_ctx.get("pnl_pct"))
    liquidity_drop_pct = _to_float(current_ctx.get("liquidity_drop_pct"))

    if pnl_pct <= float(settings.EXIT_SCALP_STOP_LOSS_PCT):
        return _full("scalp_stop_loss", ["stop_loss_triggered"])

    if liquidity_drop_pct >= float(settings.EXIT_SCALP_LIQUIDITY_DROP_PCT):
        return _full("trend_liquidity_breakdown", ["liquidity_breakdown_triggered"])

    if hold_sec >= int(settings.EXIT_SCALP_MAX_HOLD_SEC):
        return _full("scalp_max_hold_timeout", ["max_hold_timeout"])

    if hold_sec >= int(settings.EXIT_SCALP_RECHECK_SEC) and pnl_pct > 0:
        flags: list[str] = []
        entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})

        entry_volume = _to_float(entry_snapshot.get("volume_velocity"))
        now_volume = _to_float(current_ctx.get("volume_velocity_now", current_ctx.get("volume_velocity")))
        if entry_volume > 0 and now_volume < entry_volume * float(settings.EXIT_SCALP_VOLUME_VELOCITY_DECAY):
            flags.append("volume_velocity_decay")

        entry_x_score = _to_float(entry_snapshot.get("x_validation_score"))
        now_x_score = _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score")))
        if entry_x_score > 0 and now_x_score < entry_x_score * float(settings.EXIT_SCALP_X_SCORE_DECAY):
            flags.append("x_score_decay")

        now_buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")))
        if now_buy_pressure < float(settings.EXIT_SCALP_BUY_PRESSURE_FLOOR):
            flags.append("buy_pressure_below_floor")

        bundle_delta = _to_float(current_ctx.get("bundle_cluster_delta"))
        if bundle_delta < 0:
            flags.append("bundle_cluster_negative_delta")

        if flags:
            if "volume_velocity_decay" in flags:
                reason = "scalp_momentum_decay_after_recheck"
            elif "x_score_decay" in flags:
                reason = "scalp_x_validation_collapse"
            elif "buy_pressure_below_floor" in flags:
                reason = "scalp_buy_pressure_breakdown"
            else:
                reason = "scalp_momentum_decay_after_recheck"
            return _full(reason, flags)

    return _hold()


def evaluate_trend_exit(position_ctx: dict, current_ctx: dict, settings: Any) -> dict:
    pnl_pct = _to_float(current_ctx.get("pnl_pct"))
    buy_pressure = _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure")))
    liquidity_drop_pct = _to_float(current_ctx.get("liquidity_drop_pct"))
    x_delta = _to_float(current_ctx.get("x_validation_score_delta"))

    if pnl_pct <= float(settings.EXIT_TREND_HARD_STOP_PCT):
        return _full("trend_hard_stop", ["stop_loss_triggered"])

    if buy_pressure < float(settings.EXIT_TREND_BUY_PRESSURE_FLOOR):
        return _full("scalp_buy_pressure_breakdown", ["buy_pressure_below_floor"])

    if liquidity_drop_pct >= float(settings.EXIT_TREND_LIQUIDITY_DROP_PCT):
        return _full("trend_liquidity_breakdown", ["liquidity_breakdown_triggered"])

    if x_delta < 0:
        entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})
        entry_x = _to_float(entry_snapshot.get("x_validation_score"))
        now_x = _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score")))
        if entry_x > 0 and now_x < entry_x * float(settings.EXIT_SCALP_X_SCORE_DECAY):
            return _full("trend_social_confirmation_collapse", ["x_score_decay"])

    if "holder_growth_now" in current_ctx and _to_float(current_ctx.get("holder_growth_now")) <= 0 and bool(current_ctx.get("holder_growth_negative_persistent")):
        return _full("trend_social_confirmation_collapse", ["holder_growth_collapse"])

    partial_1_taken = _partial_taken(position_ctx, 1)
    partial_2_taken = _partial_taken(position_ctx, 2)

    if not partial_1_taken and pnl_pct >= float(settings.EXIT_TREND_PARTIAL1_PCT):
        return {
            "exit_decision": "PARTIAL_EXIT",
            "exit_fraction": 0.33,
            "exit_reason": "trend_partial_take_profit_1",
            "exit_flags": ["partial_take_profit_1"],
            "exit_warnings": [],
        }

    if partial_1_taken and not partial_2_taken and pnl_pct >= float(settings.EXIT_TREND_PARTIAL2_PCT):
        return {
            "exit_decision": "PARTIAL_EXIT",
            "exit_fraction": 0.50,
            "exit_reason": "trend_partial_take_profit_2",
            "exit_flags": ["partial_take_profit_2"],
            "exit_warnings": [],
        }

    return _hold()
