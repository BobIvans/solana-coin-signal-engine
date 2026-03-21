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
    ENTRY_TREND_MULTI_CLUSTER_MIN = 3
    ENTRY_TREND_CLUSTER_CONCENTRATION_MAX = 0.55
    ENTRY_TREND_DEV_SELL_MAX = 0.02
    ENTRY_SCALP_BUNDLE_COUNT_MIN = 2
    ENTRY_REGIME_CONFIDENCE_FLOOR_TREND = 0.55
    ENTRY_REGIME_CONFIDENCE_FLOOR_SCALP = 0.40
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
        "bundle_count_first_60s": 3,
        "bundle_timing_from_liquidity_add_min": 0.8,
        "bundle_success_rate": 0.8,
        "bundle_composition_dominant": "buy-only",
        "bundle_failure_retry_pattern": 1,
        "bundle_wallet_clustering_score": 0.55,
        "cluster_concentration_ratio": 0.3,
        "num_unique_clusters_first_60s": 4,
        "creator_in_cluster_flag": False,
        "continuation_confidence": 0.78,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.76,
        "linkage_risk_score": 0.12,
    }


def test_trend_takes_precedence_when_fully_confirmed():
    result = decide_entry(_token(), DummySettings())
    assert result["entry_decision"] == "TREND"
    assert result["recommended_position_pct"] > 0
    assert result["expected_hold_class"] in {"medium", "long"}
    assert result["regime_confidence"] > 0


def test_ignore_has_zero_size():
    token = _token()
    token["rug_verdict"] = "IGNORE"
    result = decide_entry(token, DummySettings())
    assert result["entry_decision"] == "IGNORE"
    assert result["recommended_position_pct"] == 0
    assert result["base_position_pct"] == 0
    assert result["effective_position_pct"] == 0
    assert result["sizing_multiplier"] == 0
    assert result["expected_hold_class"] == "none"


def test_missing_required_under_failclosed_ignored():
    token = _token()
    token.pop("final_score")
    result = decide_entry(token, DummySettings())
    assert result["entry_decision"] == "IGNORE"
    assert result["entry_reason"] == "partial_data_failclosed"
    assert "entry_failclosed_missing_fields" in result["entry_flags"]
    assert result["regime_blockers"] == ["entry_failclosed_missing_fields"]


def test_entry_result_contract_includes_new_regime_outputs():
    result = decide_entry(_token(), DummySettings())
    assert 0 <= result["regime_confidence"] <= 1
    assert isinstance(result["regime_reason_flags"], list)
    assert isinstance(result["regime_blockers"], list)
    assert result["expected_hold_class"] in {"short", "medium", "long", "none"}
    assert result["base_position_pct"] == result["recommended_position_pct"]
    assert result["effective_position_pct"] <= result["base_position_pct"]
    assert isinstance(result["sizing_reason_codes"], list)
    assert "sizing_origin" in result
    assert "evidence_quality_score" in result


def test_creator_linked_cluster_blocks_trend_but_keeps_scalp_available():
    token = _token()
    token["creator_in_cluster_flag"] = True
    token["cluster_concentration_ratio"] = 0.8

    result = decide_entry(token, DummySettings())
    assert result["entry_decision"] == "SCALP"
    assert result["expected_hold_class"] == "short"
    assert "trend_creator_cluster_linked" in result["regime_blockers"]


def test_entry_result_propagates_wallet_family_summary_fields():
    token = _token()
    token.update({
        "smart_wallet_family_ids": ["fam_a"],
        "smart_wallet_independent_family_ids": ["ifam_a"],
        "smart_wallet_family_origins": ["graph_evidence"],
        "smart_wallet_family_statuses": ["ok"],
        "smart_wallet_family_reason_codes": ["shared_cluster"],
        "smart_wallet_family_unique_count": 1,
        "smart_wallet_independent_family_unique_count": 1,
        "smart_wallet_family_confidence_max": 0.74,
        "smart_wallet_family_member_count_max": 3,
        "smart_wallet_family_shared_funder_flag": True,
        "smart_wallet_family_creator_link_flag": False,
    })
    result = decide_entry(token, DummySettings())
    assert result["smart_wallet_family_ids"] == ["fam_a"]
    assert result["smart_wallet_family_confidence_max"] == 0.74
    assert result["smart_wallet_family_shared_funder_flag"] is True
