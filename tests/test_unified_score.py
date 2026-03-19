import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.unified_score import score_token
from config.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]


def _base_token() -> dict:
    return {
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "EXAMPLE",
        "name": "Example Coin",
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
    }


BUNDLE_COMPONENT_KEYS = {
    "bundle_aggression_bonus",
    "organic_multi_cluster_bonus",
    "single_cluster_penalty",
    "creator_cluster_penalty",
    "bundle_sell_heavy_penalty",
    "retry_manipulation_penalty",
}

CONTINUATION_COMPONENT_KEYS = {
    "organic_buyer_flow_bonus",
    "liquidity_refill_bonus",
    "smart_wallet_dispersion_bonus",
    "x_author_velocity_bonus",
    "seller_reentry_bonus",
    "shock_recovery_bonus",
    "cluster_distribution_risk_penalty",
}


def test_unified_score_strong_token_watch_or_entry(monkeypatch):
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "45")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "35")
    settings = load_settings()
    out = score_token(_base_token(), settings)
    assert out["final_score"] >= 35
    assert out["regime_candidate"] in {"WATCHLIST", "ENTRY_CANDIDATE"}


def test_unified_score_x_degraded_flag(monkeypatch):
    monkeypatch.setenv("UNIFIED_SCORE_ENTRY_THRESHOLD", "45")
    monkeypatch.setenv("UNIFIED_SCORE_WATCH_THRESHOLD", "35")
    settings = load_settings()
    token = _base_token()
    token["x_status"] = "degraded"
    out = score_token(token, settings)
    assert "x_degraded" in out["score_flags"]
    assert out["regime_candidate"] in {"IGNORE", "WATCHLIST", "ENTRY_CANDIDATE"}


def test_unified_score_rug_ignore_hard_override(monkeypatch):
    settings = load_settings()
    token = _base_token()
    token["rug_verdict"] = "IGNORE"
    out = score_token(token, settings)
    assert out["regime_candidate"] == "IGNORE"
    assert out["final_score"] <= 35


def test_no_bundle_data_stays_neutral_safe():
    settings = load_settings()
    token = _base_token()
    for field in (
        "bundle_count_first_60s",
        "bundle_size_value",
        "unique_wallets_per_bundle_avg",
        "bundle_timing_from_liquidity_add_min",
        "bundle_success_rate",
        "bundle_composition_dominant",
        "bundle_tip_efficiency",
        "bundle_failure_retry_pattern",
        "cross_block_bundle_correlation",
        "bundle_wallet_clustering_score",
        "cluster_concentration_ratio",
        "num_unique_clusters_first_60s",
        "creator_in_cluster_flag",
    ):
        token.pop(field, None)
    out = score_token(token, settings)
    assert out["final_score"] >= 0
    for key in BUNDLE_COMPONENT_KEYS:
        assert key in out
        assert out[key] == 0.0


def test_legacy_payload_without_continuation_fields_stays_neutral_safe():
    settings = load_settings()
    out = score_token(_base_token(), settings)
    assert out["final_score"] >= 0
    for key in CONTINUATION_COMPONENT_KEYS:
        assert key in out
        assert out[key] == 0.0


def test_strong_continuation_fixture_gets_bounded_positive_lift():
    settings = load_settings()
    token = {
        **_base_token(),
        "net_unique_buyers_60s": 18,
        "liquidity_refill_ratio_120s": 1.75,
        "smart_wallet_dispersion_score": 0.88,
        "x_author_velocity_5m": 2.6,
        "seller_reentry_ratio": 0.68,
        "liquidity_shock_recovery_sec": 26,
    }
    out = score_token(token, settings)
    assert out["organic_buyer_flow_bonus"] > 0
    assert out["liquidity_refill_bonus"] > 0
    assert out["smart_wallet_dispersion_bonus"] > 0
    assert (
        out["organic_buyer_flow_bonus"]
        <= settings.UNIFIED_SCORE_ORGANIC_BUYER_FLOW_MAX
    )
    assert (
        out["liquidity_refill_bonus"] <= settings.UNIFIED_SCORE_LIQUIDITY_REFILL_MAX
    )
    assert (
        out["smart_wallet_dispersion_bonus"]
        <= settings.UNIFIED_SCORE_SMART_WALLET_DISPERSION_MAX
    )
    assert "continuation_quality_supported" in out["score_flags"]


def test_weak_continuation_fixture_stays_neutral_or_low():
    settings = load_settings()
    token = {
        **_base_token(),
        "net_unique_buyers_60s": 1,
        "liquidity_refill_ratio_120s": 0.82,
        "smart_wallet_dispersion_score": 0.24,
        "x_author_velocity_5m": 1.02,
        "seller_reentry_ratio": 0.08,
        "liquidity_shock_recovery_sec": 240,
    }
    out = score_token(token, settings)
    assert out["organic_buyer_flow_bonus"] == 0.0
    assert out["liquidity_refill_bonus"] == 0.0
    assert out["smart_wallet_dispersion_bonus"] == 0.0
    assert out["x_author_velocity_bonus"] == 0.0
    assert out["seller_reentry_bonus"] == 0.0
    assert out["shock_recovery_bonus"] == 0.0


def test_cluster_distribution_risk_penalty_applies_when_sell_concentration_is_high():
    settings = load_settings()
    token = {**_base_token(), "cluster_sell_concentration_120s": 0.86}
    out = score_token(token, settings)
    assert out["cluster_distribution_risk_penalty"] > 0
    assert "cluster_distribution_risk" in out["score_flags"]


def test_x_author_velocity_bonus_applies():
    settings = load_settings()
    token = {**_base_token(), "x_author_velocity_5m": 2.2}
    out = score_token(token, settings)
    assert out["x_author_velocity_bonus"] > 0
    assert "x_author_velocity_expanding" in out["score_flags"]


def test_shock_recovery_bonus_applies():
    settings = load_settings()
    token = {**_base_token(), "liquidity_shock_recovery_sec": 22}
    out = score_token(token, settings)
    assert out["shock_recovery_bonus"] > 0
    assert "liquidity_shock_recovered_fast" in out["score_flags"]


def test_strong_organic_bundle_gets_bounded_positive_lift():
    settings = load_settings()
    token = {
        **_base_token(),
        "bundle_count_first_60s": 5,
        "bundle_size_value": 42000.0,
        "unique_wallets_per_bundle_avg": 4.4,
        "bundle_timing_from_liquidity_add_min": 0.2,
        "bundle_success_rate": 0.95,
        "bundle_tip_efficiency": 0.84,
        "cross_block_bundle_correlation": 0.18,
        "bundle_wallet_clustering_score": 0.18,
        "cluster_concentration_ratio": 0.29,
        "num_unique_clusters_first_60s": 5,
        "creator_in_cluster_flag": False,
    }
    out = score_token(token, settings)
    assert out["bundle_aggression_bonus"] > 0
    assert out["organic_multi_cluster_bonus"] > 0
    assert (
        out["bundle_aggression_bonus"] <= settings.UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX
    )
    assert (
        out["organic_multi_cluster_bonus"]
        <= settings.UNIFIED_SCORE_MULTI_CLUSTER_BONUS_MAX
    )
    assert "organic_multi_cluster_participation" in out["score_flags"]


def test_single_cluster_concentration_applies_penalty():
    settings = load_settings()
    token = {
        **_base_token(),
        "bundle_wallet_clustering_score": 0.94,
        "cluster_concentration_ratio": 0.93,
        "num_unique_clusters_first_60s": 1,
    }
    out = score_token(token, settings)
    assert out["single_cluster_penalty"] > 0
    assert "single_cluster_concentration" in out["score_flags"]


def test_creator_linked_bundle_applies_penalty():
    settings = load_settings()
    token = {**_base_token(), "creator_in_cluster_flag": True}
    out = score_token(token, settings)
    assert (
        out["creator_cluster_penalty"] == settings.UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY
    )
    assert "creator_cluster_linked" in out["score_flags"]


def test_sell_only_bundle_applies_penalty():
    settings = load_settings()
    token = {**_base_token(), "bundle_composition_dominant": "sell-only"}
    out = score_token(token, settings)
    assert (
        out["bundle_sell_heavy_penalty"]
        == settings.UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX
    )
    assert "bundle_sell_heavy" in out["score_flags"]


def test_retry_heavy_bundle_applies_penalty():
    settings = load_settings()
    token = {**_base_token(), "bundle_failure_retry_pattern": 5}
    out = score_token(token, settings)
    assert (
        out["retry_manipulation_penalty"]
        == settings.UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX
    )
    assert "bundle_retry_pattern_suspicious" in out["score_flags"]


def test_score_payload_contract_includes_new_component_keys():
    jsonschema = pytest.importorskip("jsonschema")
    settings = load_settings()
    token = score_token(_base_token(), settings)
    schema = json.loads(
        (ROOT / "schemas" / "unified_score.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(token, schema)
    for key in BUNDLE_COMPONENT_KEYS:
        assert key in token
    for key in CONTINUATION_COMPONENT_KEYS:
        assert key in token
