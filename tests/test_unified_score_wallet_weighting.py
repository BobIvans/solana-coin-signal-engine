
import json
from pathlib import Path

import pytest

from scoring.unified_score import (
    DEFAULT_WALLET_WEIGHTING_MODE,
    score_token,
    score_tokens,
)


def _base_token(**overrides):
    token = {
        "mint": "mint_1",
        "token_id": "mint_1",
        "symbol": "TEST",
        "x_score": 80,
        "liquidity_usd": 50000,
        "buy_pressure": 0.70,
        "holder_growth_5m": 20,
        "rug_status": "pass",
        "wallet_registry_status": "validated",
        "smart_wallet_score_sum": 12.0,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_tier2_hits": 0,
        "smart_wallet_tier3_hits": 0,
        "smart_wallet_early_entry_hits": 1,
        "smart_wallet_active_hits": 1,
        "smart_wallet_watch_hits": 0,
        "smart_wallet_conviction_bonus": 1.0,
        "smart_wallet_registry_confidence": "high",
        "timestamp": "2026-03-18T10:00:00Z",
    }
    token.update(overrides)
    return token


def test_default_mode_is_shadow():
    assert DEFAULT_WALLET_WEIGHTING_MODE == "shadow"


def test_off_mode_preserves_pre_wallet_score():
    token = score_token(_base_token(), wallet_weighting_mode="off")
    assert token["final_score"] == token["final_score_pre_wallet"]
    assert token["wallet_score_component_applied"] == 0.0
    assert token["wallet_weighting_effective_mode"] == "off"


def test_shadow_mode_computes_component_but_does_not_change_final_score():
    token = score_token(_base_token(), wallet_weighting_mode="shadow")
    assert token["wallet_score_component_raw"] > 0.0
    assert token["wallet_score_component_applied"] == 0.0
    assert token["final_score"] == token["final_score_pre_wallet"]


def test_on_mode_applies_bounded_wallet_adjustment():
    token = score_token(_base_token(), wallet_weighting_mode="on")
    assert token["wallet_score_component_applied"] > 0.0
    assert token["final_score"] > token["final_score_pre_wallet"]
    assert token["wallet_score_component_applied"] <= 8.0


def test_degraded_registry_forces_zero_wallet_adjustment():
    token = score_token(
        _base_token(wallet_registry_status="degraded"),
        wallet_weighting_mode="on",
    )
    assert token["wallet_score_component_raw"] == 0.0
    assert token["wallet_score_component_applied"] == 0.0
    assert token["wallet_weighting_effective_mode"] == "degraded_zero"
    assert token["final_score"] == token["final_score_pre_wallet"]


def test_tier1_scores_above_tier2_and_tier3():
    t1 = score_token(_base_token(smart_wallet_tier1_hits=1, smart_wallet_tier2_hits=0, smart_wallet_tier3_hits=0), "on")
    t2 = score_token(_base_token(smart_wallet_tier1_hits=0, smart_wallet_tier2_hits=1, smart_wallet_tier3_hits=0), "on")
    t3 = score_token(_base_token(smart_wallet_tier1_hits=0, smart_wallet_tier2_hits=0, smart_wallet_tier3_hits=1), "on")
    assert t1["wallet_score_component_applied"] > t2["wallet_score_component_applied"] > t3["wallet_score_component_applied"]


def test_many_weak_hits_do_not_exceed_cap():
    token = score_token(
        _base_token(
            smart_wallet_tier1_hits=0,
            smart_wallet_tier2_hits=0,
            smart_wallet_tier3_hits=20,
            smart_wallet_active_hits=20,
            smart_wallet_watch_hits=40,
            smart_wallet_score_sum=200.0,
            smart_wallet_early_entry_hits=20,
            smart_wallet_conviction_bonus=50.0,
        ),
        "on",
    )
    assert token["wallet_score_component_applied"] <= 3.0


def test_deterministic_outputs_are_stable():
    token = _base_token()
    first = score_token(token, "on")
    second = score_token(token, "on")
    assert first == second


def test_score_tokens_emits_events_and_sorted_output():
    scored, events = score_tokens(
        shortlist=[_base_token(mint="mint_b", token_id="mint_b"), _base_token(mint="mint_a", token_id="mint_a")],
        x_validated=[],
        enriched=[],
        rug_assessed=[],
        wallet_weighting_mode="shadow",
    )
    assert [row["mint"] for row in scored] == ["mint_a", "mint_b"]
    assert len(events) == 2
    assert events[0]["wallet_weighting_mode"] == "shadow"


def test_schema_validates_scored_output():
    jsonschema = pytest.importorskip("jsonschema")
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "schemas" / "unified_score.wallet_weighting.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    token = score_token(_base_token(), "on")
    jsonschema.validate(token, schema)
