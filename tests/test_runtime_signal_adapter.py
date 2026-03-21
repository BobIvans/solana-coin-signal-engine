from __future__ import annotations

from src.promotion.runtime_signal_adapter import adapt_runtime_signal, adapt_runtime_signal_batch


def test_adapter_normalizes_valid_entry_candidate():
    signal = adapt_runtime_signal(
        {
            "signal_id": "sig1",
            "token_address": "So111",
            "pair_address": "pair1",
            "entry_decision": "SCALP",
            "regime": "SCALP",
            "x_status": "healthy",
            "regime_confidence": 0.8,
            "entry_confidence": 0.75,
            "recommended_position_pct": 0.35,
            "entry_flags": ["momentum_ok"],
            "regime_blockers": [],
            "signal_ts": "2026-03-20T00:00:00+00:00",
        },
        runtime_signal_origin="entry_candidates",
        source_artifact="data/processed/entry_candidates.json",
        runtime_origin_tier="canonical",
        runtime_pipeline_origin="canonical_runtime_pipeline",
        runtime_pipeline_status="ok",
        runtime_pipeline_manifest="data/processed/runtime_signal_pipeline_manifest.json",
    )

    assert signal["signal_id"] == "sig1"
    assert signal["runtime_signal_status"] == "ok"
    assert signal["effective_signal_status"] == "eligible"
    assert signal["runtime_signal_origin"] == "entry_candidates"
    assert signal["recommended_position_pct"] == 0.35
    assert signal["runtime_origin_tier"] == "canonical"
    assert signal["runtime_pipeline_status"] == "ok"


def test_adapter_marks_degraded_partial_signal_honestly():
    signal = adapt_runtime_signal(
        {
            "token_address": "So222",
            "entry_decision": "TREND",
            "regime": "TREND",
            "x_status": "degraded",
            "regime_confidence": 0.7,
            "recommended_position_pct": 0.0,
        },
        runtime_signal_origin="entry_candidates",
    )

    assert signal["x_status"] == "degraded"
    assert signal["runtime_signal_status"] == "partial"
    assert signal["runtime_signal_partial_flag"] is True
    assert "missing_position_size" in (signal["runtime_signal_warning"] or "")


def test_adapter_preserves_optional_sizing_contract_fields():
    signal = adapt_runtime_signal(
        {
            "token_address": "So333",
            "entry_decision": "SCALP",
            "regime": "SCALP",
            "regime_confidence": 0.81,
            "recommended_position_pct": 0.35,
            "base_position_pct": 0.35,
            "effective_position_pct": 0.22,
            "sizing_multiplier": 0.6286,
            "sizing_reason_codes": ["partial_evidence_size_reduced"],
            "sizing_confidence": 0.55,
            "sizing_origin": "partial_evidence_reduced",
            "sizing_warning": "partial_evidence",
            "evidence_quality_score": 0.61,
            "evidence_conflict_flag": True,
            "partial_evidence_flag": True,
            "evidence_coverage_ratio": 0.71,
            "evidence_available": ["x", "linkage"],
            "evidence_scores": {"x": 0.68},
        },
        runtime_signal_origin="entry_candidates",
    )

    assert signal["effective_position_pct"] == 0.22
    assert signal["sizing_origin"] == "partial_evidence_reduced"
    assert signal["evidence_conflict_flag"] is True
    assert signal["partial_evidence_flag"] is True
    assert signal["evidence_available"] == ["x", "linkage"]


def test_adapter_marks_invalid_rows_without_token_address():
    signal = adapt_runtime_signal(
        {
            "entry_decision": "SCALP",
            "regime": "SCALP",
            "regime_confidence": 0.5,
            "recommended_position_pct": 0.3,
        },
        runtime_signal_origin="entry_candidates",
    )

    assert signal["runtime_signal_status"] == "invalid"
    assert "missing_token_address" in signal["blockers"]


def test_adapter_batch_accepts_mixed_rows():
    batch = adapt_runtime_signal_batch(
        [
            {"token_address": "So111", "entry_decision": "SCALP", "regime": "SCALP", "regime_confidence": 0.6, "recommended_position_pct": 0.2},
            {"entry_decision": "TREND", "regime": "TREND", "regime_confidence": 0.6, "recommended_position_pct": 0.3},
        ],
        runtime_signal_origin="entry_candidates",
    )

    assert len(batch) == 2
    assert batch[0]["runtime_signal_status"] == "partial"
    assert batch[1]["runtime_signal_status"] == "invalid"


def test_adapter_preserves_wallet_family_summary_with_null_safe_defaults():
    signal = adapt_runtime_signal(
        {
            "token_address": "So333",
            "entry_decision": "SCALP",
            "regime": "SCALP",
            "regime_confidence": 0.66,
            "recommended_position_pct": 0.2,
            "smart_wallet_family_ids": ["fam_a", "fam_b"],
            "smart_wallet_independent_family_ids": "ifam_a",
            "smart_wallet_family_origins": ["graph_evidence"],
            "smart_wallet_family_statuses": ["ok"],
            "smart_wallet_family_reason_codes": ["shared_funder"],
            "smart_wallet_family_unique_count": 2,
            "smart_wallet_independent_family_unique_count": 1,
            "smart_wallet_family_confidence_max": 0.91,
            "smart_wallet_family_member_count_max": 5,
            "smart_wallet_family_shared_funder_flag": True,
            "smart_wallet_family_creator_link_flag": False,
        },
        runtime_signal_origin="entry_candidates",
    )

    assert signal["smart_wallet_family_ids"] == ["fam_a", "fam_b"]
    assert signal["smart_wallet_independent_family_ids"] == ["ifam_a"]
    assert signal["smart_wallet_family_origins"] == ["graph_evidence"]
    assert signal["smart_wallet_family_reason_codes"] == ["shared_funder"]
    assert signal["smart_wallet_family_unique_count"] == 2
    assert signal["smart_wallet_family_confidence_max"] == 0.91
    assert signal["smart_wallet_family_member_count_max"] == 5
    assert signal["smart_wallet_family_shared_funder_flag"] is True
    assert signal["smart_wallet_family_creator_link_flag"] is False
