from __future__ import annotations

from analytics.evidence_quality import derive_evidence_quality
from analytics.evidence_weighted_sizing import compute_evidence_weighted_size, derive_sizing_confidence
from src.promotion.guards import compute_position_sizing


BASE_CONFIG = {
    "modes": {
        "expanded_paper": {
            "open_positions": True,
            "max_open_positions": 2,
            "max_trades_per_day": 20,
            "allow_regimes": ["SCALP", "TREND"],
            "position_size_scale": 1.0,
        }
    },
    "safety": {"max_daily_loss_pct": 8.0, "max_consecutive_losses": 4, "kill_switch_file": "runs/none.flag"},
    "degraded_x": {"expanded_policy": "reduced_size"},
}
BASE_STATE = {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}


def test_strong_healthy_confirmation_preserves_base_size():
    signal = {
        "signal_id": "strong",
        "token_address": "SoStrong111",
        "entry_decision": "TREND",
        "regime": "TREND",
        "recommended_position_pct": 0.42,
        "regime_confidence": 0.86,
        "runtime_signal_confidence": 0.88,
        "continuation_confidence": 0.78,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.82,
        "linkage_risk_score": 0.12,
        "bundle_wallet_clustering_score": 0.74,
        "cluster_concentration_ratio": 0.24,
        "smart_wallet_hits": 4,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_netflow_bias": 0.32,
        "x_status": "healthy",
        "x_validation_score": 82,
    }

    sizing = compute_position_sizing(signal, BASE_STATE, BASE_CONFIG)

    assert sizing["base_position_pct"] == 0.42
    assert sizing["effective_position_pct"] == 0.42
    assert sizing["sizing_multiplier"] == 1.0
    assert sizing["sizing_origin"] == "evidence_weighted"
    assert "evidence_support_preserved_base_size" in sizing["sizing_reason_codes"]
    assert sizing["partial_evidence_flag"] is False
    assert sizing["evidence_conflict_flag"] is False


def test_degraded_x_keeps_existing_policy_and_explains_reduction():
    signal = {
        "signal_id": "degraded",
        "token_address": "SoDeg111",
        "entry_decision": "SCALP",
        "regime": "SCALP",
        "recommended_position_pct": 0.40,
        "regime_confidence": 0.74,
        "runtime_signal_confidence": 0.72,
        "continuation_confidence": 0.62,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.70,
        "linkage_risk_score": 0.20,
        "bundle_wallet_clustering_score": 0.65,
        "cluster_concentration_ratio": 0.28,
        "x_status": "degraded",
        "x_validation_score": 55,
    }

    sizing = compute_position_sizing(signal, BASE_STATE, BASE_CONFIG)

    assert sizing["mode_position_scale"] == 1.0
    assert sizing["base_position_pct"] == 0.2
    assert sizing["effective_position_pct"] == 0.2
    assert sizing["effective_position_scale"] == 0.5
    assert sizing["sizing_origin"] == "degraded_x_policy"
    assert "x_status_degraded_size_reduced" in sizing["sizing_reason_codes"]


def test_partial_evidence_reduces_size_and_flags_partial():
    signal = {
        "signal_id": "partial",
        "token_address": "SoPartial111",
        "entry_decision": "SCALP",
        "regime": "SCALP",
        "recommended_position_pct": 0.35,
        "regime_confidence": 0.72,
        "runtime_signal_confidence": 0.58,
        "runtime_signal_partial_flag": True,
        "continuation_status": "missing",
        "linkage_status": "partial",
        "x_status": "healthy",
        "x_validation_score": 68,
    }

    sizing = compute_position_sizing(signal, BASE_STATE, BASE_CONFIG)

    assert sizing["partial_evidence_flag"] is True
    assert sizing["effective_position_pct"] < sizing["base_position_pct"]
    assert sizing["sizing_origin"] == "partial_evidence_reduced"
    assert "partial_evidence_size_reduced" in sizing["sizing_reason_codes"]
    assert sizing["sizing_warning"]


def test_creator_linkage_risk_materially_reduces_size():
    signal = {
        "signal_id": "risk",
        "token_address": "SoRisk111",
        "entry_decision": "TREND",
        "regime": "TREND",
        "recommended_position_pct": 0.45,
        "regime_confidence": 0.84,
        "runtime_signal_confidence": 0.79,
        "continuation_confidence": 0.72,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.81,
        "linkage_risk_score": 0.83,
        "creator_dev_link_score": 0.88,
        "creator_buyer_link_score": 0.77,
        "bundle_wallet_clustering_score": 0.70,
        "cluster_concentration_ratio": 0.42,
        "x_status": "healthy",
        "x_validation_score": 85,
    }

    sizing = compute_position_sizing(signal, BASE_STATE, BASE_CONFIG)

    assert sizing["effective_position_pct"] < 0.3
    assert sizing["sizing_origin"] == "risk_reduced"
    assert "creator_link_risk_size_reduced" in sizing["sizing_reason_codes"]


def test_conflicting_evidence_sets_conflict_flag_and_reduces_size():
    signal = {
        "signal_id": "conflict",
        "token_address": "SoConflict111",
        "entry_decision": "TREND",
        "regime": "TREND",
        "recommended_position_pct": 0.38,
        "regime_confidence": 0.85,
        "runtime_signal_confidence": 0.82,
        "continuation_confidence": 0.30,
        "continuation_status": "weak",
        "linkage_confidence": 0.78,
        "linkage_risk_score": 0.60,
        "bundle_wallet_clustering_score": 0.42,
        "cluster_concentration_ratio": 0.74,
        "x_status": "healthy",
        "x_validation_score": 76,
    }

    sizing = compute_position_sizing(signal, BASE_STATE, BASE_CONFIG)

    assert sizing["evidence_conflict_flag"] is True
    assert sizing["effective_position_pct"] < sizing["base_position_pct"]
    assert "evidence_conflict_size_reduced" in sizing["sizing_reason_codes"]
    assert "cluster_evidence_low_confidence_size_reduced" in sizing["sizing_reason_codes"]


def test_shared_evidence_quality_helper_stays_in_sync_with_sizing_summary():
    signal = {
        "signal_id": "shared_summary",
        "token_address": "SoShared111",
        "entry_decision": "TREND",
        "regime": "TREND",
        "recommended_position_pct": 0.33,
        "regime_confidence": 0.81,
        "runtime_signal_confidence": 0.77,
        "continuation_confidence": 0.66,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.72,
        "linkage_status": "ok",
        "bundle_wallet_clustering_score": 0.61,
        "cluster_concentration_ratio": 0.34,
        "smart_wallet_hits": 3,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_netflow_bias": 0.15,
        "x_status": "healthy",
        "x_validation_score": 79,
    }

    summary = derive_evidence_quality(signal)
    sizing = derive_sizing_confidence(signal, config=BASE_CONFIG)

    assert sizing["evidence_quality_score"] == summary["evidence_quality_score"]
    assert sizing["evidence_conflict_flag"] == summary["evidence_conflict_flag"]
    assert sizing["partial_evidence_flag"] == summary["partial_evidence_flag"]
    assert sizing["evidence_available"] == summary["evidence_available"]



def test_post_first_window_candidate_gets_discovery_lag_penalty_multiplier():
    signal = {
        "signal_id": "lagged",
        "token_address": "SoLag111",
        "discovery_freshness_status": "post_first_window",
        "discovery_lag_sec": 90,
        "runtime_signal_confidence": 0.8,
        "continuation_confidence": 0.7,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.7,
        "linkage_risk_score": 0.1,
        "bundle_wallet_clustering_score": 0.7,
        "cluster_concentration_ratio": 0.2,
        "x_status": "healthy",
        "x_validation_score": 80,
    }

    sizing = compute_evidence_weighted_size(signal, base_position_pct=0.5, config=BASE_CONFIG)

    assert sizing["effective_position_pct"] < 0.5
    assert "discovery_lag_penalty" in sizing["sizing_reason_codes"]
    assert sizing["discovery_lag_size_multiplier"] == 0.6
