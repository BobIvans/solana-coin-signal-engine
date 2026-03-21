import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.entry_sizing import compute_entry_confidence, compute_entry_position_contract, compute_recommended_position_pct


class DummySettings:
    ENTRY_SCALP_SCORE_MIN = 82
    ENTRY_TREND_SCORE_MIN = 86
    ENTRY_MAX_BASE_POSITION_PCT = 1.0
    ENTRY_DEGRADED_X_SIZE_MULTIPLIER = 0.5
    ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER = 0.6
    ENTRY_SELECTOR_FAILCLOSED = True


def _token():
    return {
        "token_address": "So111",
        "final_score": 89,
        "regime_candidate": "ENTRY_CANDIDATE",
        "rug_score": 0.15,
        "rug_verdict": "PASS",
        "buy_pressure": 0.85,
        "volume_velocity": 5,
        "first30s_buy_ratio": 0.8,
        "bundle_cluster_score": 0.7,
        "bundle_wallet_clustering_score": 0.68,
        "x_validation_score": 70,
        "x_validation_delta": 5,
        "x_status": "ok",
        "dev_sell_pressure_5m": 0,
        "lp_burn_confirmed": True,
        "mint_revoked": True,
        "freeze_revoked": True,
        "continuation_confidence": 0.72,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.74,
        "linkage_risk_score": 0.1,
        "cluster_concentration_ratio": 0.28,
        "smart_wallet_hits": 2,
        "runtime_signal_confidence": 0.78,
    }


def test_confidence_bounded_and_positive_for_entry():
    token = _token()
    value = compute_entry_confidence(token, {"entry_decision": "SCALP"}, DummySettings())
    assert 0 < value <= 1


def test_size_zero_on_ignore_decision():
    token = _token()
    size = compute_recommended_position_pct(token, {"entry_decision": "IGNORE", "entry_confidence": 0.7, "entry_flags": []}, DummySettings())
    assert size == 0


def test_size_reduced_for_degraded_x_and_partial_data():
    token = _token()
    token["x_status"] = "degraded"
    token["enrichment_status"] = "partial"
    decision = {"entry_decision": "SCALP", "entry_confidence": 0.9, "entry_flags": []}
    size = compute_recommended_position_pct(token, decision, DummySettings())
    assert size < 0.9
    assert "x_degraded_size_reduced" in decision["entry_flags"]
    assert "partial_data_size_reduced" in decision["entry_flags"]


def test_entry_position_contract_emits_canonical_fields():
    token = _token()
    contract = compute_entry_position_contract(token, {"entry_decision": "SCALP", "entry_flags": []}, DummySettings())
    assert contract["recommended_position_pct"] > 0
    assert contract["base_position_pct"] == contract["recommended_position_pct"]
    assert 0 <= contract["effective_position_pct"] <= contract["base_position_pct"]
    assert isinstance(contract["sizing_reason_codes"], list)
    assert "evidence_quality_score" in contract


def test_linkage_risk_reduces_effective_size():
    token = _token()
    token["linkage_risk_score"] = 0.85
    token["creator_dev_link_score"] = 0.82
    contract = compute_entry_position_contract(token, {"entry_decision": "SCALP", "entry_flags": []}, DummySettings())
    assert contract["effective_position_pct"] < contract["recommended_position_pct"]
    assert "creator_link_risk_size_reduced" in contract["sizing_reason_codes"]


def test_weak_continuation_reduces_effective_size():
    token = _token()
    token["continuation_confidence"] = 0.3
    token["continuation_status"] = "weak"
    contract = compute_entry_position_contract(token, {"entry_decision": "SCALP", "entry_flags": []}, DummySettings())
    assert contract["effective_position_pct"] < contract["recommended_position_pct"]
    assert any(code.startswith("continuation_") for code in contract["sizing_reason_codes"])
