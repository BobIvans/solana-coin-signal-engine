import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer_metrics import (
    compute_exit_reason_metrics,
    compute_friction_metrics,
    compute_health_metrics,
    compute_portfolio_metrics,
    compute_regime_metrics,
)


def _closed_positions():
    return [
        {"regime": "SCALP", "net_pnl_sol": 0.01, "net_pnl_pct": 10, "hold_sec": 10, "exit_reason": "a", "partial_exit_count": 0, "x_status": "healthy"},
        {"regime": "SCALP", "net_pnl_sol": -0.005, "net_pnl_pct": -5, "hold_sec": 20, "exit_reason": "b", "partial_exit_count": 1, "x_status": "degraded"},
        {"regime": "TREND", "net_pnl_sol": 0.02, "net_pnl_pct": 8, "hold_sec": 60, "exit_reason": "a", "partial_exit_count": 1, "x_status": "healthy"},
    ]


def test_portfolio_metrics_core_values():
    metrics = compute_portfolio_metrics({"starting_equity_sol": 0.1, "unrealized_pnl_sol": 0.001, "equity_sol": 0.126}, _closed_positions())
    assert metrics["total_positions_closed"] == 3
    assert metrics["winrate_total"] == 2 / 3
    assert round(metrics["profit_factor_total"], 4) == 6.0


def test_regime_and_exit_metrics_present():
    regime = compute_regime_metrics(_closed_positions())
    exit_metrics = compute_exit_reason_metrics(_closed_positions())
    assert "SCALP" in regime["winrate_by_regime"]
    assert exit_metrics["exit_reason_distribution"]["a"] == 2


def test_friction_metrics_rates():
    trades = [
        {"status": "filled", "slippage_bps": 100, "priority_fee_sol": 0.00001, "gross_pnl_sol": 0.01, "net_pnl_sol": 0.009},
        {"status": "failed", "slippage_bps": 200, "priority_fee_sol": 0.00002, "partial_fill": True, "gross_pnl_sol": 0.0, "net_pnl_sol": 0.0},
    ]
    friction = compute_friction_metrics(trades)
    assert friction["failed_fill_rate"] == 0.5
    assert friction["partial_fill_rate"] == 0.5


def test_health_metrics_surface_runtime_quality_context():
    trades = [
        {"partial_evidence_flag": True},
        {"partial_evidence_flag": False},
    ]
    health = compute_health_metrics(
        trades,
        _closed_positions(),
        runtime_health_summary={
            "runtime_current_state_live_count": 2,
            "runtime_current_state_fallback_count": 1,
            "runtime_current_state_stale_count": 1,
            "tx_window_partial_count": 2,
            "tx_window_truncated_count": 1,
            "unresolved_replay_row_count": 1,
        },
    )
    assert health["runtime_stale_state_share"] == 0.25
    assert health["partial_evidence_trade_share"] == 0.5
    assert round(health["degraded_x_trade_share"], 4) == round(1 / 3, 4)
    assert health["tx_coverage_quality_summary"]["tx_window_partial_count"] == 2
