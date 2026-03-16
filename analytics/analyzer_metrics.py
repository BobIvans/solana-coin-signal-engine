"""Core metric computations for post-run analyzer (PR-10)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any


def _safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def compute_portfolio_metrics(state: dict[str, Any], closed_positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute top-level portfolio metrics over reconstructed closed positions."""

    pnl_pcts = [float(p.get("net_pnl_pct", 0.0)) for p in closed_positions]
    net_pnls = [float(p.get("net_pnl_sol", 0.0)) for p in closed_positions]

    wins = [p for p in closed_positions if float(p.get("net_pnl_sol", 0.0)) > 0]
    gross_profit = sum(float(p.get("net_pnl_sol", 0.0)) for p in closed_positions if float(p.get("net_pnl_sol", 0.0)) > 0)
    gross_loss = sum(float(p.get("net_pnl_sol", 0.0)) for p in closed_positions if float(p.get("net_pnl_sol", 0.0)) < 0)

    equity_points = [float(state.get("starting_equity_sol", state.get("equity_sol", 0.0) - sum(net_pnls)))]
    running = equity_points[0]
    for value in net_pnls:
        running += value
        equity_points.append(running)

    peak = equity_points[0] if equity_points else 0.0
    max_drawdown = 0.0
    for point in equity_points:
        peak = max(peak, point)
        max_drawdown = max(max_drawdown, peak - point)

    realized = sum(net_pnls)
    unrealized = float(state.get("unrealized_pnl_sol", 0.0))

    return {
        "total_signals": int(state.get("total_signals", 0)),
        "total_entries_attempted": int(state.get("total_entries_attempted", 0)),
        "total_fills_successful": int(state.get("total_fills_successful", 0)),
        "total_positions_closed": len(closed_positions),
        "total_positions_open": int(state.get("total_positions_open", 0)),
        "realized_pnl_sol": realized,
        "unrealized_pnl_sol": unrealized,
        "net_pnl_sol": realized + unrealized,
        "equity_sol": float(state.get("equity_sol", float(state.get("starting_equity_sol", 0.0)) + realized + unrealized)),
        "winrate_total": _safe_div(len(wins), len(closed_positions)),
        "profit_factor_total": gross_profit if gross_loss == 0 else gross_profit / abs(gross_loss),
        "avg_trade_pnl_pct": statistics.fmean(pnl_pcts) if pnl_pcts else 0.0,
        "median_trade_pnl_pct": statistics.median(pnl_pcts) if pnl_pcts else 0.0,
        "max_drawdown_sol": max_drawdown,
    }


def compute_regime_metrics(closed_positions: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in closed_positions:
        grouped[str(position.get("regime", "unknown"))].append(position)

    winrate_by_regime: dict[str, float] = {}
    profit_factor_by_regime: dict[str, float] = {}
    avg_pnl_by_regime: dict[str, float] = {}
    median_hold_sec_by_regime: dict[str, float] = {}
    failed_fill_rate_by_regime: dict[str, float] = {}
    partial_exit_usage_by_regime: dict[str, float] = {}

    for regime, items in grouped.items():
        wins = [p for p in items if float(p.get("net_pnl_sol", 0.0)) > 0]
        gross_profit = sum(float(p.get("net_pnl_sol", 0.0)) for p in items if float(p.get("net_pnl_sol", 0.0)) > 0)
        gross_loss = sum(float(p.get("net_pnl_sol", 0.0)) for p in items if float(p.get("net_pnl_sol", 0.0)) < 0)
        hold_values = [float(p.get("hold_sec", 0.0)) for p in items]
        pnl_values = [float(p.get("net_pnl_pct", 0.0)) for p in items]
        failed = sum(1 for p in items if bool(p.get("had_failed_fill")))
        partial = sum(1 for p in items if int(p.get("partial_exit_count", 0)) > 0)

        winrate_by_regime[regime] = _safe_div(len(wins), len(items))
        profit_factor_by_regime[regime] = gross_profit if gross_loss == 0 else gross_profit / abs(gross_loss)
        avg_pnl_by_regime[regime] = statistics.fmean(pnl_values) if pnl_values else 0.0
        median_hold_sec_by_regime[regime] = statistics.median(hold_values) if hold_values else 0.0
        failed_fill_rate_by_regime[regime] = _safe_div(failed, len(items))
        partial_exit_usage_by_regime[regime] = _safe_div(partial, len(items))

    return {
        "winrate_by_regime": winrate_by_regime,
        "profit_factor_by_regime": profit_factor_by_regime,
        "avg_pnl_by_regime": avg_pnl_by_regime,
        "median_hold_sec_by_regime": median_hold_sec_by_regime,
        "failed_fill_rate_by_regime": failed_fill_rate_by_regime,
        "partial_exit_usage_by_regime": partial_exit_usage_by_regime,
    }


def compute_exit_reason_metrics(closed_positions: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in closed_positions:
        reason = str(position.get("exit_reason_final", position.get("exit_reason", "unknown")))
        grouped[reason].append(position)

    distribution = Counter({reason: len(items) for reason, items in grouped.items()})
    avg_pnl_pct_by_exit_reason: dict[str, float] = {}
    winrate_by_exit_reason: dict[str, float] = {}
    median_hold_sec_by_exit_reason: dict[str, float] = {}

    for reason, items in grouped.items():
        pnl_values = [float(p.get("net_pnl_pct", 0.0)) for p in items]
        hold_values = [float(p.get("hold_sec", 0.0)) for p in items]
        wins = [p for p in items if float(p.get("net_pnl_sol", 0.0)) > 0]
        avg_pnl_pct_by_exit_reason[reason] = statistics.fmean(pnl_values) if pnl_values else 0.0
        winrate_by_exit_reason[reason] = _safe_div(len(wins), len(items))
        median_hold_sec_by_exit_reason[reason] = statistics.median(hold_values) if hold_values else 0.0

    return {
        "exit_reason_distribution": dict(distribution),
        "count_by_exit_reason": dict(distribution),
        "avg_pnl_pct_by_exit_reason": avg_pnl_pct_by_exit_reason,
        "winrate_by_exit_reason": winrate_by_exit_reason,
        "median_hold_sec_by_exit_reason": median_hold_sec_by_exit_reason,
    }


def compute_friction_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    slippage = [float(t.get("slippage_bps", 0.0)) for t in trades if t.get("slippage_bps") is not None]
    priority_fees = [float(t.get("priority_fee_sol", 0.0)) for t in trades if t.get("priority_fee_sol") is not None]
    failed_count = sum(1 for t in trades if str(t.get("status", "")).lower() == "failed")
    partial_count = sum(1 for t in trades if bool(t.get("partial_fill")) or str(t.get("fill_status", "")).lower() == "partial")
    gross_values = [float(t.get("gross_pnl_sol", 0.0)) for t in trades if t.get("gross_pnl_sol") is not None]
    net_values = [float(t.get("net_pnl_sol", 0.0)) for t in trades if t.get("net_pnl_sol") is not None]

    gap_values: list[float] = []
    for gross, net in zip(gross_values, net_values):
        gap_values.append(abs(gross - net))

    return {
        "avg_slippage_bps": statistics.fmean(slippage) if slippage else 0.0,
        "median_slippage_bps": statistics.median(slippage) if slippage else 0.0,
        "avg_priority_fee_sol": statistics.fmean(priority_fees) if priority_fees else 0.0,
        "failed_fill_rate": _safe_div(failed_count, len(trades)),
        "partial_fill_rate": _safe_div(partial_count, len(trades)),
        "avg_net_vs_gross_pnl_gap": statistics.fmean(gap_values) if gap_values else 0.0,
    }
