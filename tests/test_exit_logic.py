import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.exit_logic import decide_exit


class DummySettings:
    EXIT_ENGINE_FAILCLOSED = True
    EXIT_DEV_SELL_HARD = True
    EXIT_RUG_FLAG_HARD = True
    EXIT_SCALP_STOP_LOSS_PCT = -10
    EXIT_SCALP_RECHECK_SEC = 18
    EXIT_SCALP_MAX_HOLD_SEC = 120
    EXIT_SCALP_BUY_PRESSURE_FLOOR = 0.60
    EXIT_SCALP_LIQUIDITY_DROP_PCT = 20
    EXIT_SCALP_VOLUME_VELOCITY_DECAY = 0.70
    EXIT_SCALP_X_SCORE_DECAY = 0.70
    EXIT_TREND_HARD_STOP_PCT = -18
    EXIT_TREND_PARTIAL1_PCT = 35
    EXIT_TREND_PARTIAL2_PCT = 100
    EXIT_TREND_BUY_PRESSURE_FLOOR = 0.50
    EXIT_TREND_LIQUIDITY_DROP_PCT = 25
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
    EXIT_CONTRACT_VERSION = "exit_engine_v1"


def _position(entry_decision="SCALP"):
    return {
        "position_id": "p1",
        "token_address": "So111",
        "symbol": "EX",
        "entry_decision": entry_decision,
        "entry_time": "2026-03-15T12:30:41Z",
        "entry_price_usd": 1.0,
        "entry_snapshot": {
            "volume_velocity": 4.8,
            "x_validation_score": 71.4,
            "bundle_cluster_score": 0.66,
            "liquidity_usd": 30000,
            "bundle_count_first_60s": 2,
            "bundle_composition_dominant": "buy-only",
            "creator_in_cluster_flag": True,
        },
    }


def _current():
    return {
        "now_ts": "2026-03-15T12:31:04Z",
        "price_usd_now": 1.10,
        "buy_pressure_now": 0.80,
        "volume_velocity_now": 4.6,
        "liquidity_usd_now": 29500,
        "x_validation_score_now": 70.0,
        "x_status_now": "ok",
        "bundle_cluster_score_now": 0.67,
        "dev_sell_pressure_now": 0.0,
        "rug_flag_now": False,
    }


def test_failclosed_missing_current_state_forces_safe_exit():
    out = decide_exit(_position(), {"price_usd_now": 1.0}, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "missing_current_state_failclosed"
    assert out["exit_status"] == "partial"


def test_valid_hold_stays_hold():
    out = decide_exit(_position(), _current(), DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert out["exit_fraction"] == 0.0
    assert out["exit_snapshot"]["bundle_count_first_60s"] == 2
    assert out["exit_snapshot"]["bundle_composition_dominant"] == "buy-only"
    assert out["exit_snapshot"]["creator_in_cluster_flag"] is True


def test_legacy_payload_without_new_bundle_cluster_fields_remains_safe():
    out = decide_exit(_position(), _current(), DummySettings())
    assert out["exit_reason"] == "hold_conditions_intact"
    assert out["exit_warnings"] == []
    assert "cluster_sell_concentration_120s" not in out["exit_snapshot"]


def test_retry_spike_warning_is_preserved_in_result_contract():
    current = {
        **_current(),
        "bundle_failure_retry_pattern_now": 2.3,
        "bundle_failure_retry_delta": 1.1,
        "cross_block_bundle_correlation_now": 0.40,
    }
    out = decide_exit(_position(), current, DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert "bundle_failure_spike" in out["exit_warnings"]
    assert out["exit_snapshot"]["bundle_failure_retry_pattern_now"] == 2.3


def test_trend_creator_cluster_risk_forces_full_exit():
    current = {
        **_current(),
        "buy_pressure_now": 0.68,
        "creator_in_cluster_flag_now": True,
        "creator_cluster_activity_now": 0.86,
        "cluster_concentration_ratio_now": 0.74,
        "cross_block_bundle_correlation_now": 0.82,
        "wallet_features": {"smart_wallet_netflow_bias": -0.2},
    }
    out = decide_exit(_position(entry_decision="TREND"), current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "creator_cluster_exit_risk"
    assert "creator_cluster_activity_now" in out["exit_snapshot"]


def test_hard_exit_precedence_overrides_trend_partial_logic():
    current = {
        **_current(),
        "price_usd_now": 2.0,
        "buy_pressure_now": 0.43,
        "cluster_sell_concentration_120s": 0.90,
        "cluster_concentration_ratio_now": 0.87,
        "bundle_composition_dominant_now": "distribution",
        "wallet_features": {"smart_wallet_netflow_bias": -0.5},
    }
    out = decide_exit(_position(entry_decision="TREND"), current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "cluster_dump_detected"
    assert out["exit_fraction"] == 1.0


def test_legacy_trend_payload_without_continuation_metrics_remains_safe():
    out = decide_exit(_position(entry_decision="TREND"), _current(), DummySettings())
    assert out["exit_decision"] == "HOLD"
    assert "liquidity_refill_ratio_120s" not in out["exit_snapshot"]


def test_trend_continuation_failure_is_captured_in_snapshot_and_reason():
    current = {
        **_current(),
        "buy_pressure_now": 0.56,
        "liquidity_refill_ratio_120s": 0.61,
        "liquidity_shock_recovery_sec": 220,
        "seller_reentry_ratio": 0.11,
        "cluster_sell_concentration_120s": 0.74,
        "net_unique_buyers_60s": -2,
        "smart_wallet_dispersion_score": 0.22,
        "x_author_velocity_5m": 0.15,
    }
    out = decide_exit(_position(entry_decision="TREND"), current, DummySettings())
    assert out["exit_decision"] == "FULL_EXIT"
    assert out["exit_reason"] == "failed_liquidity_refill_exit"
    assert out["exit_snapshot"]["liquidity_refill_ratio_120s"] == 0.61
    assert out["exit_snapshot"]["seller_reentry_ratio"] == 0.11
    assert out["exit_snapshot"]["liquidity_shock_recovery_sec"] == 220
    assert "x_author_velocity_cooling" in out["exit_warnings"]
