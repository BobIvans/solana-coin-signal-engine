from __future__ import annotations

from analytics.offline_feature_importance import _build_target_value


def test_profitable_trade_target_uses_positive_net_pnl():
    assert _build_target_value({"net_pnl_pct": 2.5}, "profitable_trade_flag") is True
    assert _build_target_value({"net_pnl_pct": 0.0}, "profitable_trade_flag") is False
    assert _build_target_value({}, "profitable_trade_flag") is None


def test_trend_success_target_requires_multiple_supporting_signals():
    row = {
        "net_pnl_pct": 6.0,
        "trend_survival_15m": 0.62,
        "mfe_pct_240s": 9.0,
        "time_to_first_profit_sec": 120,
    }
    assert _build_target_value(row, "trend_success_flag") is True
    assert _build_target_value({"net_pnl_pct": 6.0, "trend_survival_15m": 0.2, "mfe_pct_240s": 3.0}, "trend_success_flag") is False
    assert _build_target_value({}, "trend_success_flag") is None


def test_fast_failure_target_triggers_on_early_loss_or_failure_reason():
    assert _build_target_value({"net_pnl_pct": -4.0, "hold_sec": 180}, "fast_failure_flag") is True
    assert _build_target_value({"mae_pct_240s": -7.0}, "fast_failure_flag") is True
    assert _build_target_value({"exit_reason_final": "breakdown_stop"}, "fast_failure_flag") is True
    assert _build_target_value({"net_pnl_pct": 5.0, "hold_sec": 600, "mae_pct_240s": -2.0}, "fast_failure_flag") is False

def test_trend_success_target_is_stable_when_only_two_signals_exist():
    assert _build_target_value({"net_pnl_pct": 6.0, "trend_survival_15m": 0.62}, "trend_success_flag") is True
    assert _build_target_value({"net_pnl_pct": 6.0, "trend_survival_15m": 0.10}, "trend_success_flag") is False
