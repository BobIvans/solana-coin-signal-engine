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
    EXIT_CONTRACT_VERSION = "exit_engine_v1"


def _position():
    return {
        "position_id": "p1",
        "token_address": "So111",
        "symbol": "EX",
        "entry_decision": "SCALP",
        "entry_time": "2026-03-15T12:30:41Z",
        "entry_price_usd": 1.0,
        "entry_snapshot": {
            "volume_velocity": 4.8,
            "x_validation_score": 71.4,
            "bundle_cluster_score": 0.66,
            "liquidity_usd": 30000,
            "bundle_count_first_60s": 2,
            "bundle_composition_dominant": "snipers",
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
    assert out["exit_snapshot"]["bundle_composition_dominant"] == "snipers"
    assert out["exit_snapshot"]["creator_in_cluster_flag"] is True
