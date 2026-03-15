import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.entry_logic import decide_entry


class DummySettings:
    ENTRY_SELECTOR_FAILCLOSED = True
    ENTRY_SCALP_SCORE_MIN = 82
    ENTRY_TREND_SCORE_MIN = 86
    ENTRY_SCALP_MAX_AGE_SEC = 480
    ENTRY_RUG_MAX_SCALP = 0.30
    ENTRY_RUG_MAX_TREND = 0.20
    ENTRY_BUY_PRESSURE_MIN_SCALP = 0.75
    ENTRY_BUY_PRESSURE_MIN_TREND = 0.65
    ENTRY_FIRST30S_BUY_RATIO_MIN = 0.65
    ENTRY_BUNDLE_CLUSTER_MIN = 0.55
    ENTRY_SCALP_MIN_X_SCORE = 50
    ENTRY_TREND_MIN_X_SCORE = 65
    ENTRY_HOLDER_GROWTH_MIN_TREND = 20
    ENTRY_SMART_WALLET_HITS_MIN_TREND = 2
    ENTRY_MAX_BASE_POSITION_PCT = 1.0
    ENTRY_DEGRADED_X_SIZE_MULTIPLIER = 0.5
    ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER = 0.6
    ENTRY_CONTRACT_VERSION = "entry_selector_v1"
    RUG_DEV_SELL_PRESSURE_HARD = 0.25


def _token():
    return {
        "token_address": "So111",
        "symbol": "EX",
        "name": "Example",
        "regime_candidate": "ENTRY_CANDIDATE",
        "final_score": 90,
        "age_sec": 120,
        "rug_score": 0.1,
        "rug_verdict": "PASS",
        "buy_pressure": 0.8,
        "first30s_buy_ratio": 0.8,
        "bundle_cluster_score": 0.7,
        "volume_velocity": 4.5,
        "x_validation_score": 70,
        "x_validation_delta": 8,
        "x_status": "ok",
        "holder_growth_5m": 25,
        "smart_wallet_hits": 3,
        "dev_sell_pressure_5m": 0,
        "lp_burn_confirmed": True,
        "mint_revoked": True,
        "freeze_revoked": True,
    }


def test_trend_takes_precedence_over_scalp():
    result = decide_entry(_token(), DummySettings())
    assert result["entry_decision"] == "TREND"
    assert result["recommended_position_pct"] > 0


def test_ignore_has_zero_size():
    token = _token()
    token["rug_verdict"] = "IGNORE"
    result = decide_entry(token, DummySettings())
    assert result["entry_decision"] == "IGNORE"
    assert result["recommended_position_pct"] == 0


def test_missing_required_under_failclosed_ignored():
    token = _token()
    token.pop("final_score")
    result = decide_entry(token, DummySettings())
    assert result["entry_decision"] == "IGNORE"
    assert result["entry_reason"] == "partial_data_failclosed"
