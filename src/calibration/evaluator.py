"""Candidate evaluation over replay artifacts."""

from __future__ import annotations

import statistics


def _trade_day(trade: dict) -> str:
    ts = trade.get("entry_time_utc") or trade.get("timestamp") or trade.get("timestamp_utc")
    return ts.split("T", 1)[0]


def _passes_entry(trade: dict, params: dict) -> bool:
    regime = str(trade.get("regime", "")).upper()
    final_score = float(trade.get("final_score", 0.0))
    buy_pressure = float(trade.get("buy_pressure", trade.get("first30s_buy_ratio", 0.0)))
    volume_velocity = float(trade.get("volume_velocity", 0.0))
    rug_score = float(trade.get("rug_score", 0.0))
    smart_hits = int(trade.get("smart_wallet_hits", 0))

    if regime == "SCALP" and final_score < float(params.get("scalp_final_score_min", 0)):
        return False
    if regime == "TREND" and final_score < float(params.get("trend_final_score_min", 0)):
        return False
    if buy_pressure < float(params.get("buy_pressure_min", 0.0)):
        return False
    if volume_velocity < float(params.get("volume_velocity_min", 0.0)):
        return False
    if regime == "SCALP" and rug_score > float(params.get("rug_score_max_scalp", 1.0)):
        return False
    if regime == "TREND" and rug_score > float(params.get("rug_score_max_trend", 1.0)):
        return False
    if smart_hits < int(params.get("smart_wallet_hits_min", 0)):
        return False
    return True


def _apply_exit_adjustments(trade: dict, params: dict) -> dict:
    adjusted = dict(trade)
    pnl_pct = float(adjusted.get("pnl_pct", 0.0))
    regime = str(adjusted.get("regime", "")).upper()

    if regime == "SCALP":
        decay = float(params.get("scalp_velocity_decay_ratio", 0.70))
        max_hold = float(params.get("scalp_max_hold_sec", 120))
        pressure_fail = float(params.get("scalp_buy_pressure_fail", 0.60))
        hold = float(adjusted.get("hold_seconds", max_hold))
        pressure = float(adjusted.get("buy_pressure", adjusted.get("first30s_buy_ratio", 1.0)))
        if hold > max_hold:
            pnl_pct *= 0.9
        if pressure < pressure_fail:
            pnl_pct *= 0.85
        pnl_pct *= max(0.5, min(decay / 0.70, 1.2))
    elif regime == "TREND":
        partial_1 = float(params.get("trend_partial_1_pct", 35))
        partial_2 = float(params.get("trend_partial_2_pct", 100))
        pressure_fail = float(params.get("trend_buy_pressure_fail", 0.50))
        liq_drop_fail = float(params.get("trend_liquidity_drop_fail_pct", 25))
        pressure = float(adjusted.get("buy_pressure", adjusted.get("first30s_buy_ratio", 1.0)))
        liq_drop = float(adjusted.get("liquidity_drop_pct", 0.0))
        pnl_pct *= (partial_1 + partial_2) / 135.0
        if pressure < pressure_fail:
            pnl_pct *= 0.9
        if liq_drop > liq_drop_fail:
            pnl_pct *= 0.8

    adjusted["pnl_pct"] = pnl_pct
    return adjusted


def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "winrate": 0.0,
            "expectancy": 0.0,
            "median_pnl_pct": 0.0,
            "max_drawdown_est": 0.0,
        }

    pnls = [float(trade.get("pnl_pct", 0.0)) for trade in trades]
    wins = sum(1 for pnl in pnls if pnl > 0)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return {
        "trades": len(trades),
        "winrate": wins / len(trades),
        "expectancy": sum(pnls) / len(pnls),
        "median_pnl_pct": statistics.median(pnls),
        "max_drawdown_est": max_dd,
    }


def detect_regime_collapse(metrics: dict) -> bool:
    scalp_trades = int(metrics.get("regimes", {}).get("scalp_trades", 0))
    trend_trades = int(metrics.get("regimes", {}).get("trend_trades", 0))
    total = scalp_trades + trend_trades
    if total == 0:
        return True
    return scalp_trades == 0 or trend_trades == 0


def evaluate_candidate(candidate_config: dict, replay_artifacts: dict, split: dict) -> dict:
    trades = replay_artifacts.get("trades", [])
    filtered = [_apply_exit_adjustments(trade, candidate_config) for trade in trades if _passes_entry(trade, candidate_config)]

    train_days = set(split["train_days"])
    validation_days = set(split["validation_days"])
    train_trades = [trade for trade in filtered if _trade_day(trade) in train_days]
    validation_trades = [trade for trade in filtered if _trade_day(trade) in validation_days]

    validation_scalp = [trade for trade in validation_trades if str(trade.get("regime", "")).upper() == "SCALP"]
    validation_trend = [trade for trade in validation_trades if str(trade.get("regime", "")).upper() == "TREND"]

    result = {
        "train": compute_metrics(train_trades),
        "validation": compute_metrics(validation_trades),
        "regimes": {
            "scalp_trades": len(validation_scalp),
            "trend_trades": len(validation_trend),
        },
    }
    result["regime_collapsed"] = detect_regime_collapse(result)
    return result
