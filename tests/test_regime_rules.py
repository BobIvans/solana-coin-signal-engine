import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.regime_rules import is_scalp_candidate, is_trend_candidate, should_ignore


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
    RUG_DEV_SELL_PRESSURE_HARD = 0.25


def _base_token():
    return {
        "token_address": "So111",
        "regime_candidate": "ENTRY_CANDIDATE",
        "final_score": 90,
        "age_sec": 120,
        "rug_score": 0.10,
        "rug_verdict": "PASS",
        "buy_pressure": 0.8,
        "first30s_buy_ratio": 0.8,
        "bundle_cluster_score": 0.8,
        "volume_velocity": 5,
        "dev_sell_pressure_5m": 0,
        "x_validation_score": 70,
        "x_validation_delta": 2,
        "holder_growth_5m": 30,
        "smart_wallet_hits": 3,
        "lp_burn_confirmed": True,
    }


def test_trend_eligible_on_strong_inputs():
    result = is_trend_candidate(_base_token(), DummySettings())
    assert result["eligible"] is True


def test_scalp_eligible_with_degraded_x():
    token = _base_token()
    token["x_validation_score"] = 45
    token["x_status"] = "degraded"
    result = is_scalp_candidate(token, DummySettings())
    assert result["eligible"] is True
    assert "x_degraded_size_reduced" in result["flags"]


def test_should_ignore_on_hard_rug_override():
    token = _base_token()
    token["rug_verdict"] = "IGNORE"
    result = should_ignore(token, DummySettings())
    assert result["ignore"] is True
    assert result["reason"] == "safety_override_ignore"
