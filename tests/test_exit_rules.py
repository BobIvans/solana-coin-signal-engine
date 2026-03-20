import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.exit_rules import evaluate_hard_exit, evaluate_scalp_exit, evaluate_trend_exit


class DummySettings:
    KILL_SWITCH_FILE = "runs/runtime/kill_switch.flag"
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
    EXIT_CLUSTER_SELL_CONCENTRATION_WARN = 0.72
    EXIT_CLUSTER_SELL_CONCENTRATION_HARD = 0.78
    EXIT_LIQUIDITY_REFILL_FAIL_MIN = 0.85
    EXIT_SELLER_REENTRY_WEAK_MAX = 0.20
    EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC = 180
    EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD = 2.0
    EXIT_RETRY_MANIPULATION_HARD = 5.0
    EXIT_CREATOR_CLUSTER_RISK_HARD = 0.75
    EXIT_LINKAGE_RISK_HARD = 0.78


def test_hard_exit_rug_takes_precedence():
    out = evaluate_hard_exit({}, {"rug_flag_now": True, "dev_sell_pressure_now": 0}, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "rug_flag_triggered"


def test_hard_exit_dev_sell_uses_entry_fallback():
    position = {"entry_snapshot": {"dev_sell_pressure_5m": 0.2}}
    out = evaluate_hard_exit(position, {}, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "dev_sell_detected"


def test_hard_exit_rug_uses_entry_fallback():
    position = {"entry_snapshot": {"rug_flag": True}}
    out = evaluate_hard_exit(position, {}, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "rug_flag_triggered"


def test_evaluate_hard_exit_kill_switch_forces_full_exit_before_other_rules():
    out = evaluate_hard_exit(
        {},
        {
            "kill_switch_active": True,
            "rug_flag_now": True,
            "dev_sell_pressure_now": 1.0,
            "cluster_sell_concentration_120s": 0.95,
        },
        DummySettings(),
    )
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "kill_switch_triggered"
    assert out["exit_flags"] == ["kill_switch_triggered"]


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
        "cluster_sell_concentration_120s": 0.79,
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


def test_severe_cluster_distribution_triggers_trend_exit():
    position = {"entry_snapshot": {"cluster_concentration_ratio": 0.40}}
    current = {
        "pnl_pct": 18,
        "buy_pressure_now": 0.58,
        "liquidity_drop_pct": 3,
        "x_validation_score_delta": 1,
        "cluster_sell_concentration_120s": 0.79,
        "cluster_concentration_ratio_now": 0.82,
        "liquidity_refill_ratio_120s": 0.78,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "cluster_distribution_exit"
    assert "cluster_distribution_detected" in out["exit_flags"]


def test_failed_liquidity_refill_triggers_trend_exit():
    position = {"entry_snapshot": {}}
    current = {
        "pnl_pct": 9,
        "buy_pressure_now": 0.58,
        "liquidity_drop_pct": 6,
        "x_validation_score_delta": 2,
        "liquidity_refill_ratio_120s": 0.60,
        "liquidity_shock_recovery_sec": 210,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "failed_liquidity_refill_exit"
    assert "failed_liquidity_refill_detected" in out["exit_flags"]


def test_weak_reentry_adds_warning_without_forcing_exit_alone():
    position = {"entry_snapshot": {}}
    current = {
        "pnl_pct": 12,
        "buy_pressure_now": 0.74,
        "liquidity_drop_pct": 2,
        "x_validation_score_delta": 3,
        "seller_reentry_ratio": 0.16,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert "weak_reentry_detected" in out["exit_warnings"]


def test_slow_shock_recovery_triggers_protective_trend_exit():
    position = {"entry_snapshot": {}}
    current = {
        "pnl_pct": 7,
        "buy_pressure_now": 0.55,
        "liquidity_drop_pct": 5,
        "x_validation_score_delta": 1,
        "liquidity_shock_recovery_sec": 320,
        "liquidity_refill_ratio_120s": 0.82,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "shock_not_recovered_exit"
    assert "shock_not_recovered_detected" in out["exit_flags"]


def test_high_linkage_risk_triggers_trend_exit_when_distribution_confirms():
    position = {"entry_snapshot": {"linkage_confidence": 0.72, "creator_buyer_link_score": 0.82}}
    current = {
        "pnl_pct": 16,
        "buy_pressure_now": 0.64,
        "liquidity_drop_pct": 3,
        "x_validation_score_delta": 2,
        "linkage_risk_score_now": 0.84,
        "creator_buyer_link_score_now": 0.82,
        "shared_funder_link_score_now": 0.75,
        "cluster_sell_concentration_120s": 0.76,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "linkage_risk_exit"
    assert "linkage_risk_detected" in out["exit_flags"]


def test_linkage_warning_path_uses_canonical_warning_marker_without_forcing_exit():
    position = {"entry_snapshot": {"linkage_confidence": 0.52, "creator_buyer_link_score": 0.74}}
    current = {
        "pnl_pct": 11,
        "buy_pressure_now": 0.71,
        "liquidity_drop_pct": 2,
        "x_validation_score_delta": 2,
        "linkage_risk_score_now": 0.63,
        "creator_buyer_link_score_now": 0.74,
        "shared_funder_link_score_now": 0.71,
        "cluster_sell_concentration_120s": 0.40,
        "bundle_failure_retry_pattern_now": 0.0,
    }
    out = evaluate_trend_exit(position, current, DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert "linkage_risk_detected" in out["exit_warnings"]


def test_high_linkage_risk_triggers_hard_exit_with_canonical_reason_and_flag():
    position = {"entry_snapshot": {"linkage_confidence": 0.73, "creator_buyer_link_score": 0.81}}
    current = {
        "linkage_risk_score_now": 0.88,
        "creator_buyer_link_score_now": 0.81,
        "shared_funder_link_score_now": 0.76,
        "cluster_sell_concentration_120s": 0.80,
    }
    out = evaluate_hard_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "linkage_risk_exit"
    assert "linkage_risk_detected" in out["exit_flags"]


def test_high_linkage_risk_triggers_scalp_exit_with_canonical_reason_and_flag():
    position = {"entry_snapshot": {"linkage_confidence": 0.72, "creator_buyer_link_score": 0.82}}
    current = {
        "hold_sec": 14,
        "pnl_pct": 8,
        "liquidity_drop_pct": 2,
        "buy_pressure_now": 0.72,
        "linkage_risk_score_now": 0.84,
        "creator_buyer_link_score_now": 0.82,
        "shared_funder_link_score_now": 0.75,
        "cluster_sell_concentration_120s": 0.76,
    }
    out = evaluate_scalp_exit(position, current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "linkage_risk_exit"
    assert "linkage_risk_detected" in out["exit_flags"]
