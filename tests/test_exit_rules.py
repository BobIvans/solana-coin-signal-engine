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
    EXIT_CLUSTER_DUMP_HARD = 0.82
    EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD = 0.65
    EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD = 2.0
    EXIT_RETRY_MANIPULATION_HARD = 5.0
    EXIT_CREATOR_CLUSTER_RISK_HARD = 0.75


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


def test_severe_cluster_dump_forces_trend_full_exit():
    position = {
        "entry_snapshot": {
            "bundle_composition_dominant": "buy-only",
            "cluster_concentration_ratio": 0.35,
        }
    }
    current = {
        "pnl_pct": 15,
        "buy_pressure_now": 0.42,
        "liquidity_drop_pct": 4,
        "x_validation_score_delta": 1,
        "cluster_sell_concentration_120s": 0.91,
        "cluster_concentration_ratio_now": 0.88,
        "bundle_composition_dominant_now": "distribution",
        "wallet_features": {"smart_wallet_netflow_bias": -0.4},
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "cluster_dump_detected"
    assert "cluster_dump_detected" in out["exit_flags"]


def test_retry_spike_can_warn_without_forcing_exit():
    position = {"entry_snapshot": {"bundle_failure_retry_pattern": 1}}
    current = {
        "hold_sec": 12,
        "pnl_pct": 3,
        "liquidity_drop_pct": 1,
        "buy_pressure_now": 0.85,
        "bundle_failure_retry_pattern_now": 2.4,
        "bundle_failure_retry_delta": 1.2,
        "cross_block_bundle_correlation_now": 0.35,
    }
    out = evaluate_scalp_exit(position, current, DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert "bundle_failure_spike" in out["exit_warnings"]


def test_creator_linked_risk_triggers_trend_exit():
    position = {
        "entry_snapshot": {
            "creator_in_cluster_flag": True,
            "bundle_composition_dominant": "buy-only",
        }
    }
    current = {
        "pnl_pct": 22,
        "buy_pressure_now": 0.67,
        "liquidity_drop_pct": 2,
        "x_validation_score_delta": 4,
        "creator_in_cluster_flag_now": True,
        "creator_cluster_activity_now": 0.84,
        "cluster_concentration_ratio_now": 0.72,
        "cross_block_bundle_correlation_now": 0.81,
        "wallet_features": {"smart_wallet_netflow_bias": -0.2},
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "creator_cluster_exit_risk"
    assert "creator_cluster_exit_risk" in out["exit_flags"]


def test_hard_exit_bundle_risk_overrides_scalp_recheck_logic():
    position = {"entry_snapshot": {"volume_velocity": 5.0, "x_validation_score": 70}}
    current = {
        "hold_sec": 30,
        "pnl_pct": 40,
        "liquidity_drop_pct": 0,
        "volume_velocity_now": 4.8,
        "x_validation_score_now": 69,
        "buy_pressure_now": 0.55,
        "bundle_failure_retry_pattern_now": 5.8,
        "bundle_failure_retry_delta": 2.2,
        "cross_block_bundle_correlation_now": 0.91,
        "bundle_composition_dominant_now": "sell-heavy",
        "wallet_features": {"smart_wallet_netflow_bias": -0.3},
    }
    out = evaluate_hard_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "retry_manipulation_detected"
