import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.exit_rules import evaluate_hard_exit, evaluate_scalp_exit, evaluate_trend_exit


class DummySettings:
    EXIT_DEV_SELL_HARD = True
    EXIT_RUG_FLAG_HARD = True
    EXIT_SCALP_STOP_LOSS_PCT = -10
    EXIT_SCALP_LIQUIDITY_DROP_PCT = 20
    EXIT_SCALP_MAX_HOLD_SEC = 120
    EXIT_SCALP_RECHECK_SEC = 18
    EXIT_SCALP_VOLUME_VELOCITY_DECAY = 0.70
    EXIT_SCALP_X_SCORE_DECAY = 0.70
    EXIT_SCALP_BUY_PRESSURE_FLOOR = 0.60
    EXIT_TREND_HARD_STOP_PCT = -18
    EXIT_TREND_BUY_PRESSURE_FLOOR = 0.50
    EXIT_TREND_LIQUIDITY_DROP_PCT = 25
    EXIT_TREND_PARTIAL1_PCT = 35
    EXIT_TREND_PARTIAL2_PCT = 100


def test_hard_exit_rug_takes_precedence():
    out = evaluate_hard_exit({}, {"rug_flag_now": True, "dev_sell_pressure_now": 0}, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "rug_flag_triggered"


def test_scalp_recheck_momentum_decay_full_exit():
    position = {"entry_snapshot": {"volume_velocity": 5.0, "x_validation_score": 70}}
    current = {
        "hold_sec": 20,
        "pnl_pct": 12,
        "liquidity_drop_pct": 1,
        "volume_velocity_now": 3.0,
        "x_validation_score_now": 68,
        "buy_pressure_now": 0.8,
        "bundle_cluster_delta": 0.1,
    }
    out = evaluate_scalp_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "scalp_momentum_decay_after_recheck"


def test_trend_partial_not_repeated():
    position = {"partials_taken": ["partial_1"], "entry_snapshot": {"x_validation_score": 70}}
    current = {
        "pnl_pct": 120,
        "buy_pressure_now": 0.8,
        "liquidity_drop_pct": 2,
        "x_validation_score_delta": 3,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "PARTIAL_EXIT"
    assert out["exit_reason"] == "trend_partial_take_profit_2"
