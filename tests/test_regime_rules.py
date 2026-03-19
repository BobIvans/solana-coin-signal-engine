import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.regime_rules import decide_regime, is_scalp_candidate, is_trend_candidate, should_ignore


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
    ENTRY_TREND_MULTI_CLUSTER_MIN = 3
    ENTRY_TREND_CLUSTER_CONCENTRATION_MAX = 0.55
    ENTRY_TREND_DEV_SELL_MAX = 0.02
    ENTRY_SCALP_BUNDLE_COUNT_MIN = 2
    ENTRY_REGIME_CONFIDENCE_FLOOR_TREND = 0.55
    ENTRY_REGIME_CONFIDENCE_FLOOR_SCALP = 0.40
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
        "mint_revoked": True,
        "bundle_count_first_60s": 3,
        "bundle_timing_from_liquidity_add_min": 0.8,
        "bundle_success_rate": 0.7,
        "bundle_composition_dominant": "buy-only",
        "bundle_failure_retry_pattern": 1,
        "bundle_wallet_clustering_score": 0.45,
        "cluster_concentration_ratio": 0.35,
        "num_unique_clusters_first_60s": 4,
        "creator_in_cluster_flag": False,
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


def test_decide_regime_legacy_payload_without_bundle_fields_routes_safely():
    token = _base_token()
    for field in [
        "bundle_count_first_60s",
        "bundle_timing_from_liquidity_add_min",
        "bundle_success_rate",
        "bundle_composition_dominant",
        "bundle_failure_retry_pattern",
        "bundle_wallet_clustering_score",
        "cluster_concentration_ratio",
        "num_unique_clusters_first_60s",
        "creator_in_cluster_flag",
    ]:
        token.pop(field, None)

    result = decide_regime(token, DummySettings())
    assert result["regime_decision"] == "SCALP"
    assert result["expected_hold_class"] == "short"
    assert result["regime_confidence"] > 0
    assert "trend_multi_cluster_evidence_missing" in result["warnings"]


def test_decide_regime_strong_trend_returns_medium_or_long_hold():
    result = decide_regime(_base_token(), DummySettings())
    assert result["regime_decision"] == "TREND"
    assert result["regime_confidence"] >= DummySettings.ENTRY_REGIME_CONFIDENCE_FLOOR_TREND
    assert result["expected_hold_class"] in {"medium", "long"}
    assert "trend_multi_cluster_confirmation" in result["regime_reason_flags"]


def test_decide_regime_blocks_trend_when_creator_cluster_linked():
    token = _base_token()
    token["creator_in_cluster_flag"] = True
    token["cluster_concentration_ratio"] = 0.82

    result = decide_regime(token, DummySettings())
    assert result["regime_decision"] == "SCALP"
    assert "trend_creator_cluster_linked" in result["regime_blockers"]
    assert "trend_cluster_concentration_high" in result["regime_blockers"]
    assert result["expected_hold_class"] == "short"


def test_decide_regime_allows_scalp_when_x_is_degraded_but_momentum_is_strong():
    token = _base_token()
    token["x_validation_score"] = 45
    token["x_status"] = "degraded"
    token["smart_wallet_hits"] = 1
    token["holder_growth_5m"] = 18
    token["num_unique_clusters_first_60s"] = 2

    result = decide_regime(token, DummySettings())
    assert result["regime_decision"] == "SCALP"
    assert "trend_x_degraded_without_confirmation" in result["regime_blockers"]
    assert "trend_confirmation_incomplete" in result["regime_reason_flags"]


def test_decide_regime_returns_ignore_when_evidence_is_insufficient():
    token = _base_token()
    token["final_score"] = 78
    token["buy_pressure"] = 0.55
    token["first30s_buy_ratio"] = 0.52
    token["bundle_cluster_score"] = 0.4
    token["volume_velocity"] = 1.2
    token["x_validation_score"] = 40
    token["smart_wallet_hits"] = 0
    token["holder_growth_5m"] = 10

    result = decide_regime(token, DummySettings())
    assert result["regime_decision"] == "IGNORE"
    assert result["expected_hold_class"] == "none"
    assert result["regime_confidence"] == 0
    assert result["regime_blockers"]
