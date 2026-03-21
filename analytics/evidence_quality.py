"""Shared evidence-quality summary helpers for scoring, sizing, and replay."""

from __future__ import annotations

from typing import Any, Mapping


_EVIDENCE_LANE_COUNT = 7.0
_WEAK_STATUSES = {"missing", "partial", "degraded", "weak"}
_X_STATUS_BASE = {
    "healthy": 0.65,
    "ok": 0.65,
    "confirmed": 0.65,
    "degraded": 0.4,
    "missing": 0.25,
    "error": 0.2,
    "unknown": 0.25,
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _candidate_sources(signal: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources: list[Mapping[str, Any]] = [signal]
    raw_signal = signal.get("raw_signal")
    entry_snapshot = signal.get("entry_snapshot")
    if isinstance(raw_signal, Mapping):
        sources.append(raw_signal)
    if isinstance(entry_snapshot, Mapping):
        sources.append(entry_snapshot)
    return sources


def _first_present(signal: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        for source in _candidate_sources(signal):
            if field in source and source.get(field) not in (None, ""):
                return source.get(field)
    return None


def derive_evidence_quality(
    signal: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del config  # reserved for future config-driven lane tuning

    regime_confidence = _safe_float(_first_present(signal, "regime_confidence"))
    runtime_confidence = _safe_float(_first_present(signal, "runtime_signal_confidence", "entry_confidence"))
    continuation_confidence = _safe_float(_first_present(signal, "continuation_confidence"))
    linkage_confidence = _safe_float(_first_present(signal, "linkage_confidence"))
    x_validation_score = _safe_float(_first_present(signal, "x_validation_score", "x_validation_score_entry"))

    x_status = _safe_str(_first_present(signal, "x_status")).lower() or "unknown"
    continuation_status = _safe_str(_first_present(signal, "continuation_status", "continuation_inputs_status")).lower()
    linkage_status = _safe_str(_first_present(signal, "linkage_status")).lower()
    runtime_partial_flag = bool(_first_present(signal, "runtime_signal_partial_flag"))

    evidence_scores: dict[str, float] = {}
    if regime_confidence is not None:
        evidence_scores["regime"] = round(_clamp(regime_confidence), 4)
    if runtime_confidence is not None:
        evidence_scores["runtime"] = round(_clamp(runtime_confidence), 4)
    if continuation_confidence is not None:
        evidence_scores["continuation"] = round(_clamp(continuation_confidence), 4)
    elif continuation_status:
        evidence_scores["continuation"] = 0.35 if continuation_status in _WEAK_STATUSES else 0.6
    if linkage_confidence is not None:
        evidence_scores["linkage"] = round(_clamp(linkage_confidence), 4)
    elif linkage_status:
        evidence_scores["linkage"] = 0.35 if linkage_status in {"missing", "partial", "degraded"} else 0.6

    if x_validation_score is not None:
        x_quality = _clamp(x_validation_score / 100.0)
        if x_status == "degraded":
            x_quality *= 0.7
        elif x_status in {"missing", "error", "unknown"}:
            x_quality *= 0.5
        evidence_scores["x"] = round(_clamp(x_quality), 4)
    elif x_status:
        evidence_scores["x"] = _X_STATUS_BASE.get(x_status, 0.25)

    cluster_concentration = _safe_float(_first_present(signal, "cluster_concentration_ratio"))
    bundle_cluster_score = _safe_float(_first_present(signal, "bundle_wallet_clustering_score"))
    if bundle_cluster_score is not None:
        cluster_quality = _clamp(bundle_cluster_score)
        if cluster_concentration is not None and cluster_concentration >= 0.65:
            cluster_quality *= 0.8
        evidence_scores["cluster"] = round(_clamp(cluster_quality), 4)
    elif cluster_concentration is not None:
        evidence_scores["cluster"] = round(_clamp(1.0 - cluster_concentration), 4)

    wallet_hits = _safe_float(_first_present(signal, "smart_wallet_hits", "smart_wallet_hits_entry"))
    wallet_tier1_hits = _safe_float(_first_present(signal, "smart_wallet_tier1_hits"))
    wallet_bias = _safe_float(_first_present(signal, "smart_wallet_netflow_bias"))
    wallet_components: list[float] = []
    if wallet_hits is not None:
        wallet_components.append(_clamp(wallet_hits / 5.0))
    if wallet_tier1_hits is not None:
        wallet_components.append(_clamp(wallet_tier1_hits / 2.0))
    if wallet_bias is not None:
        wallet_components.append(_clamp((wallet_bias + 1.0) / 2.0))
    if wallet_components:
        evidence_scores["wallet"] = round(sum(wallet_components) / len(wallet_components), 4)

    evidence_available = sorted(evidence_scores.keys())
    evidence_lane_count = len(evidence_available)
    evidence_coverage_ratio = round(_clamp(evidence_lane_count / _EVIDENCE_LANE_COUNT), 4)
    evidence_quality_score = round(sum(evidence_scores.values()) / evidence_lane_count, 4) if evidence_scores else 0.0

    positive_signal = any(
        score >= 0.7
        for name, score in evidence_scores.items()
        if name in {"regime", "runtime", "continuation", "cluster", "wallet"}
    )
    linkage_risk_score = _safe_float(_first_present(signal, "linkage_risk_score")) or 0.0
    creator_link_risk_score = max(
        linkage_risk_score,
        _safe_float(_first_present(signal, "creator_dev_link_score")) or 0.0,
        _safe_float(_first_present(signal, "creator_buyer_link_score")) or 0.0,
        _safe_float(_first_present(signal, "shared_funder_link_score")) or 0.0,
        _safe_float(_first_present(signal, "creator_cluster_link_score")) or 0.0,
        _safe_float(_first_present(signal, "cluster_dev_link_score")) or 0.0,
    )
    weak_signal = (
        (continuation_confidence is not None and continuation_confidence < 0.45)
        or continuation_status in _WEAK_STATUSES
        or linkage_risk_score >= 0.55
        or creator_link_risk_score >= 0.65
        or runtime_partial_flag
    )
    evidence_conflict_flag = bool(positive_signal and weak_signal)

    partial_evidence_flag = bool(
        runtime_partial_flag
        or evidence_lane_count < 4
        or continuation_status in {"missing", "partial"}
        or linkage_status in {"missing", "partial"}
        or x_status in {"missing", "error", "unknown"}
    )

    warnings: list[str] = []
    if partial_evidence_flag:
        warnings.append("partial_evidence")
    if evidence_lane_count < 3:
        warnings.append("limited_evidence_coverage")
    if evidence_quality_score < 0.5:
        warnings.append("low_evidence_quality")
    if x_status == "degraded":
        warnings.append("x_status_degraded")
    if continuation_status in _WEAK_STATUSES:
        warnings.append("continuation_support_weak_or_partial")
    if linkage_risk_score >= 0.55 or creator_link_risk_score >= 0.65:
        warnings.append("creator_or_linkage_risk_present")
    if evidence_conflict_flag:
        warnings.append("evidence_conflict")

    return {
        "evidence_coverage_ratio": evidence_coverage_ratio,
        "coverage_ratio": evidence_coverage_ratio,
        "evidence_quality_score": evidence_quality_score,
        "evidence_scores": evidence_scores,
        "evidence_available": evidence_available,
        "available_evidence": evidence_available,
        "partial_evidence_flag": partial_evidence_flag,
        "evidence_conflict_flag": evidence_conflict_flag,
        "evidence_quality_warnings": _dedupe(warnings),
        "warnings": _dedupe(warnings),
        "continuation_confidence": None if continuation_confidence is None else round(_clamp(continuation_confidence), 4),
        "runtime_confidence": None if runtime_confidence is None else round(_clamp(runtime_confidence), 4),
        "creator_link_risk_score": round(_clamp(creator_link_risk_score), 4),
        "x_status": x_status,
    }


__all__ = ["derive_evidence_quality"]
