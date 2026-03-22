from analytics.unified_score import score_token as analytics_score_token
from config.settings import load_settings
from scoring.unified_score import canonicalize_scoring_input, score_token as wrapper_score_token


def _legacy_token(**overrides):
    token = {
        "mint": "mint_path_parity",
        "token_id": "mint_path_parity",
        "symbol": "PAR",
        "x_score": 81,
        "liquidity_usd": 62000,
        "buy_pressure": 0.74,
        "holder_growth_5m": 27,
        "rug_status": "pass",
        "wallet_registry_status": "validated",
        "smart_wallet_score_sum": 12.5,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_tier2_hits": 0,
        "smart_wallet_tier3_hits": 1,
        "smart_wallet_early_entry_hits": 1,
        "smart_wallet_active_hits": 2,
        "smart_wallet_watch_hits": 0,
        "smart_wallet_conviction_bonus": 1.5,
        "smart_wallet_registry_confidence": "high",
        "timestamp": "2026-03-19T12:00:00Z",
    }
    token.update(overrides)
    return token


def _assert_parity(mode: str) -> None:
    settings = load_settings()
    legacy = _legacy_token()
    canonical = canonicalize_scoring_input(legacy)
    wrapper = wrapper_score_token(legacy, wallet_weighting_mode=mode)
    direct = analytics_score_token(
        canonical,
        settings,
        wallet_weighting_mode=mode,
        scored_at=canonical["timestamp"],
    )
    for key in (
        "final_score_pre_wallet",
        "final_score",
        "regime_candidate",
        "wallet_weighting_mode",
        "wallet_weighting_effective_mode",
        "wallet_registry_status",
        "wallet_score_component_raw",
        "wallet_score_component_applied",
        "wallet_score_component_applied_shadow",
        "wallet_score_component_capped",
        "wallet_score_component_reason",
        "wallet_score_explain",
        "wallet_adjustment",
        "discovery_lag_score_penalty",
        "score_flags",
        "score_warnings",
        "scored_at",
    ):
        assert wrapper[key] == direct[key]


def test_wrapper_matches_direct_analytics_off_mode():
    _assert_parity("off")


def test_wrapper_matches_direct_analytics_shadow_mode():
    _assert_parity("shadow")


def test_wrapper_matches_direct_analytics_on_mode():
    _assert_parity("on")


def test_wrapper_legacy_aliases_match_canonical_payload_semantics():
    settings = load_settings()
    legacy = _legacy_token(mint="mint_alias", token_id="mint_alias", x_score=77)
    canonical = canonicalize_scoring_input(legacy)

    wrapper = wrapper_score_token(legacy, wallet_weighting_mode="shadow")
    direct = analytics_score_token(
        canonical,
        settings,
        wallet_weighting_mode="shadow",
        scored_at=canonical["timestamp"],
    )

    assert wrapper["token_address"] == direct["token_address"] == "mint_alias"
    assert wrapper["x_validation_bonus"] == direct["x_validation_bonus"]
    assert wrapper["final_score_pre_wallet"] == direct["final_score_pre_wallet"]
    assert wrapper["final_score"] == direct["final_score"]
