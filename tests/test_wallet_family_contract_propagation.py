from __future__ import annotations

from types import SimpleNamespace

from analytics.unified_score import score_token
from src.promotion.runtime_signal_adapter import adapt_runtime_signal
from src.replay.historical_replay_harness import _build_trade_feature_row
from trading.entry_logic import decide_entry


class _EntrySettings:
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


class _ScoreSettings(SimpleNamespace):
    pass


def _token() -> dict:
    return {
        "token_address": "tok_wallet_family",
        "symbol": "WFAM",
        "name": "Wallet Family Token",
        "fast_prescore": 88.0,
        "first30s_buy_ratio": 0.78,
        "bundle_cluster_score": 0.65,
        "priority_fee_avg_first_min": 0.0012,
        "x_validation_score": 79.0,
        "x_validation_delta": 12.0,
        "x_status": "ok",
        "top20_holder_share": 0.42,
        "first50_holder_conc_est": 0.57,
        "holder_entropy_est": 2.9,
        "holder_growth_5m": 40,
        "dev_sell_pressure_5m": 0.07,
        "pumpfun_to_raydium_sec": 140,
        "smart_wallet_hits": 4,
        "rug_score": 0.31,
        "rug_verdict": "WATCH",
        "mint_revoked": True,
        "freeze_revoked": True,
        "lp_burn_confirmed": True,
        "lp_locked_flag": False,
        "x_duplicate_text_ratio": 0.25,
        "x_promoter_concentration": 0.2,
        "x_unique_authors_visible": 10,
        "x_contract_mention_presence": 1,
        "enrichment_status": "ok",
        "rug_status": "ok",
        "final_score": 91.5,
        "regime_candidate": "ENTRY_CANDIDATE",
        "age_sec": 120,
        "buy_pressure": 0.8,
        "volume_velocity": 4.5,
        "smart_wallet_family_ids": ["fam_a", "fam_b"],
        "smart_wallet_independent_family_ids": ["ifam_a"],
        "smart_wallet_family_origins": ["graph_evidence", "mixed_evidence"],
        "smart_wallet_family_statuses": ["ok", "partial"],
        "smart_wallet_family_reason_codes": ["shared_funder", "shared_cluster"],
        "smart_wallet_family_unique_count": 2,
        "smart_wallet_independent_family_unique_count": 1,
        "smart_wallet_family_confidence_max": 0.93,
        "smart_wallet_family_member_count_max": 6,
        "smart_wallet_family_shared_funder_flag": True,
        "smart_wallet_family_creator_link_flag": False,
    }


def test_wallet_family_summary_propagates_scored_to_entry_to_runtime_to_matrix(monkeypatch):
    from config.settings import load_settings

    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "45")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "35")
    scored = score_token(_token(), load_settings())
    assert scored["smart_wallet_family_ids"] == ["fam_a", "fam_b"]
    assert scored["smart_wallet_family_confidence_max"] == 0.93

    entry = decide_entry({**_token(), **scored}, _EntrySettings())
    assert entry["smart_wallet_family_ids"] == ["fam_a", "fam_b"]
    assert entry["smart_wallet_family_shared_funder_flag"] is True

    runtime_signal = adapt_runtime_signal(entry, runtime_signal_origin="entry_candidates")
    assert runtime_signal["smart_wallet_family_reason_codes"] == ["shared_funder", "shared_cluster"]
    assert runtime_signal["smart_wallet_family_member_count_max"] == 6

    matrix_row = _build_trade_feature_row(
        run_id="wallet_family_matrix",
        wallet_weighting="disabled",
        dry_run=True,
        config_hash="cfg",
        base_context={**entry, "features": {}, "entry_snapshot": {}},
        signal=runtime_signal,
        trade={"decision": "paper_enter", "entry_decision": entry["entry_decision"]},
        replay_data_status="historical_partial",
        replay_resolution_status="partial",
        replay_input_origin="historical",
        synthetic_assist_flag=False,
    )
    assert matrix_row["smart_wallet_family_ids"] == ["fam_a", "fam_b"]
    assert matrix_row["smart_wallet_family_confidence_max"] == 0.93
    assert matrix_row["smart_wallet_family_shared_funder_flag"] is True


def test_wallet_family_summary_defaults_are_explicit_in_runtime_and_matrix():
    runtime_signal = adapt_runtime_signal(
        {
            "token_address": "tok_defaults",
            "entry_decision": "IGNORE",
            "regime": "IGNORE",
            "regime_confidence": 0.0,
            "recommended_position_pct": 0.0,
        },
        runtime_signal_origin="entry_candidates",
    )
    assert runtime_signal["smart_wallet_family_ids"] == []
    assert runtime_signal["smart_wallet_family_confidence_max"] == 0.0
    assert runtime_signal["smart_wallet_family_shared_funder_flag"] is False

    matrix_row = _build_trade_feature_row(
        run_id="wallet_family_defaults",
        wallet_weighting="disabled",
        dry_run=True,
        config_hash="cfg",
        base_context={"token_address": "tok_defaults", "features": {}, "entry_snapshot": {}},
        signal={"token_address": "tok_defaults", "entry_decision": "IGNORE"},
        trade={"decision": "paper_enter", "entry_decision": "IGNORE"},
        replay_data_status="historical_partial",
        replay_resolution_status="partial",
        replay_input_origin="historical",
        synthetic_assist_flag=False,
    )
    assert matrix_row["smart_wallet_family_ids"] == []
    assert matrix_row["smart_wallet_family_confidence_max"] == 0.0
    assert matrix_row["smart_wallet_family_shared_funder_flag"] is False
