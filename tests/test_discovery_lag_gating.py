import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.entry_logic import decide_entry
from trading.entry_sizing import compute_recommended_position_pct


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
    DISCOVERY_LAG_TREND_BLOCK_SEC = 60
    DISCOVERY_POST_FIRST_WINDOW_HARD_BLOCK_ENABLED = True
    DISCOVERY_POST_FIRST_WINDOW_SCALP_MAX_LAG_SEC = 120
    DISCOVERY_LAG_SCALP_SIZE_REDUCTION_SEC = 45
    DISCOVERY_LAG_SIZE_MULTIPLIER = 0.6


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


def test_native_first_window_candidate_has_no_lag_penalty():
    token = _token()
    token["discovery_freshness_status"] = "native_first_window"
    token["discovery_lag_sec"] = 5

    size = compute_recommended_position_pct(token, {"entry_decision": "SCALP", "entry_confidence": 0.9, "entry_flags": []}, DummySettings())

    assert size > 0.5


def test_post_first_window_candidate_blocks_trend():
    token = _token()
    token["discovery_freshness_status"] = "post_first_window"
    token["discovery_lag_sec"] = 90
    token["delayed_launch_window_flag"] = True

    result = decide_entry(token, DummySettings())

    assert result["entry_decision"] == "SCALP"
    assert result["discovery_lag_blocked_trend"] is True


def test_large_lag_candidate_gets_size_reduction_or_ignore():
    token = _token()
    token["discovery_freshness_status"] = "post_first_window"
    token["discovery_lag_sec"] = 180
    token["delayed_launch_window_flag"] = True

    result = decide_entry(token, DummySettings())

    assert result["entry_decision"] == "IGNORE"
