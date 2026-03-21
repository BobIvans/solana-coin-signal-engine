from __future__ import annotations

import pytest

from analytics.evidence_quality import derive_evidence_quality
from analytics.score_components import compute_evidence_quality_penalties
from analytics.unified_score import score_token
from config.settings import load_settings


def _base_token() -> dict:
    return {
        "token_address": "SoEvidence1111111111111111111111111111111111",
        "symbol": "EVD",
        "name": "Evidence Coin",
        "fast_prescore": 84.0,
        "x_validation_score": 82.0,
        "x_validation_delta": 10.0,
        "rug_score": 0.22,
        "rug_verdict": "WATCH",
        "holder_growth_5m": 34,
        "top20_holder_share": 0.38,
        "dev_sell_pressure_5m": 0.05,
        "smart_wallet_hits": 4,
        "enrichment_status": "ok",
        "rug_status": "ok",
    }


def test_healthy_evidence_summary_and_penalties_stay_clean():
    settings = load_settings()
    token = {
        **_base_token(),
        "regime_confidence": 0.84,
        "runtime_signal_confidence": 0.88,
        "continuation_confidence": 0.79,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.83,
        "linkage_status": "ok",
        "bundle_wallet_clustering_score": 0.78,
        "cluster_concentration_ratio": 0.24,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_netflow_bias": 0.24,
        "x_status": "healthy",
    }
    summary = derive_evidence_quality(token)
    penalties = compute_evidence_quality_penalties(token, settings, summary)
    assert summary["partial_evidence_flag"] is False
    assert summary["evidence_conflict_flag"] is False
    assert penalties["partial_evidence_penalty"] == 0.0
    assert penalties["low_confidence_evidence_penalty"] == 0.0


def test_partial_evidence_applies_fixed_penalty():
    settings = load_settings()
    token = {
        **_base_token(),
        "regime_confidence": 0.72,
        "runtime_signal_confidence": 0.55,
        "runtime_signal_partial_flag": True,
        "continuation_status": "missing",
        "linkage_status": "partial",
        "x_status": "missing",
        "x_validation_score": None,
    }
    summary = derive_evidence_quality(token)
    penalties = compute_evidence_quality_penalties(token, settings, summary)
    assert summary["partial_evidence_flag"] is True
    assert penalties["partial_evidence_penalty"] == pytest.approx(settings.UNIFIED_SCORE_PARTIAL_EVIDENCE_PENALTY)


def test_low_evidence_quality_penalty_is_bounded_and_positive():
    settings = load_settings()
    token = {
        **_base_token(),
        "regime_confidence": 0.32,
        "runtime_signal_confidence": 0.28,
        "continuation_confidence": 0.24,
        "continuation_status": "weak",
        "linkage_confidence": 0.30,
        "linkage_status": "partial",
        "bundle_wallet_clustering_score": 0.22,
        "cluster_concentration_ratio": 0.82,
        "x_status": "missing",
        "x_validation_score": None,
    }
    summary = derive_evidence_quality(token)
    penalties = compute_evidence_quality_penalties(token, settings, summary)
    assert penalties["low_confidence_evidence_penalty"] > 0.0
    assert penalties["low_confidence_evidence_penalty"] <= settings.UNIFIED_SCORE_LOW_CONFIDENCE_EVIDENCE_PENALTY_MAX


def test_conflict_evidence_gets_higher_low_confidence_penalty_than_non_conflict():
    settings = load_settings()
    baseline = {
        **_base_token(),
        "regime_confidence": 0.81,
        "runtime_signal_confidence": 0.80,
        "continuation_confidence": 0.58,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.72,
        "linkage_status": "ok",
        "bundle_wallet_clustering_score": 0.58,
        "cluster_concentration_ratio": 0.48,
        "x_status": "healthy",
    }
    conflict = dict(baseline)
    conflict.update(
        {
            "continuation_confidence": 0.22,
            "continuation_status": "weak",
            "linkage_risk_score": 0.62,
            "cluster_concentration_ratio": 0.74,
        }
    )
    base_penalty = compute_evidence_quality_penalties(baseline, settings, derive_evidence_quality(baseline))
    conflict_summary = derive_evidence_quality(conflict)
    conflict_penalty = compute_evidence_quality_penalties(conflict, settings, conflict_summary)
    assert conflict_summary["evidence_conflict_flag"] is True
    assert conflict_penalty["low_confidence_evidence_penalty"] > base_penalty["low_confidence_evidence_penalty"]


def test_unified_score_emits_explicit_evidence_contract_fields():
    settings = load_settings()
    token = {
        **_base_token(),
        "runtime_signal_partial_flag": True,
        "continuation_status": "missing",
        "linkage_status": "partial",
        "x_status": "missing",
        "x_validation_score": None,
    }
    out = score_token(token, settings)
    assert out["partial_evidence_flag"] is True
    assert out["partial_evidence_penalty"] > 0.0
    assert "evidence_quality_score" in out
    assert "evidence_available" in out
    assert "evidence_scores" in out
