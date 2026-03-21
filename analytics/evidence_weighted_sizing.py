"""Conservative evidence-weighted sizing helpers for runtime and replay flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from analytics.evidence_quality import derive_evidence_quality

DEFAULT_SIZING_POLICY: dict[str, float | bool] = {
    "enabled": True,
    "min_multiplier": 0.2,
    "max_multiplier": 1.0,
    "partial_evidence_multiplier": 0.75,
    "evidence_conflict_multiplier": 0.7,
    "creator_link_risk_multiplier": 0.55,
    "moderate_link_risk_multiplier": 0.75,
    "low_continuation_multiplier": 0.75,
    "low_cluster_confidence_multiplier": 0.8,
    "low_runtime_confidence_multiplier": 0.85,
    "missing_evidence_multiplier": 0.65,
    "low_quality_multiplier": 0.8,
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


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


def _policy_overrides(config: Mapping[str, Any] | None) -> dict[str, float | bool]:
    policy = dict(DEFAULT_SIZING_POLICY)
    sizing_cfg = (config or {}).get("sizing", {}) if isinstance(config, Mapping) else {}
    if not isinstance(sizing_cfg, Mapping):
        return policy
    mapping = {
        "enabled": "EVIDENCE_WEIGHTED_SIZING_ENABLED",
        "min_multiplier": "SIZING_MIN_MULTIPLIER",
        "max_multiplier": "SIZING_MAX_MULTIPLIER",
        "partial_evidence_multiplier": "SIZING_PARTIAL_DATA_MULTIPLIER",
        "evidence_conflict_multiplier": "SIZING_EVIDENCE_CONFLICT_MULTIPLIER",
        "creator_link_risk_multiplier": "SIZING_CREATOR_LINK_RISK_MULTIPLIER",
        "low_continuation_multiplier": "SIZING_LOW_CONTINUATION_MULTIPLIER",
    }
    for key, alias in mapping.items():
        for candidate in (key, alias):
            if candidate in sizing_cfg:
                policy[key] = sizing_cfg[candidate]
                break
    for key in list(DEFAULT_SIZING_POLICY):
        if key in policy and isinstance(DEFAULT_SIZING_POLICY[key], bool):
            policy[key] = bool(policy[key])
        elif key in policy:
            numeric = _safe_float(policy[key])
            policy[key] = DEFAULT_SIZING_POLICY[key] if numeric is None else numeric
    return policy


def derive_sizing_confidence(signal: Mapping[str, Any], *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    policy = _policy_overrides(config)
    evidence_quality = derive_evidence_quality(signal, config=config)
    sizing_confidence = min(
        float(evidence_quality["evidence_quality_score"]),
        float(evidence_quality["evidence_coverage_ratio"])
        if float(evidence_quality["evidence_coverage_ratio"]) > 0
        else float(evidence_quality["evidence_quality_score"]),
    )
    if evidence_quality["evidence_conflict_flag"]:
        sizing_confidence *= float(policy["evidence_conflict_multiplier"])
    if evidence_quality["partial_evidence_flag"]:
        sizing_confidence *= 0.9

    return {
        "coverage_ratio": float(evidence_quality["evidence_coverage_ratio"]),
        "evidence_coverage_ratio": float(evidence_quality["evidence_coverage_ratio"]),
        "evidence_quality_score": float(evidence_quality["evidence_quality_score"]),
        "evidence_scores": dict(evidence_quality["evidence_scores"]),
        "available_evidence": list(evidence_quality["evidence_available"]),
        "evidence_available": list(evidence_quality["evidence_available"]),
        "partial_evidence_flag": bool(evidence_quality["partial_evidence_flag"]),
        "evidence_conflict_flag": bool(evidence_quality["evidence_conflict_flag"]),
        "warnings": list(evidence_quality["evidence_quality_warnings"]),
        "evidence_quality_warnings": list(evidence_quality["evidence_quality_warnings"]),
        "sizing_confidence": round(_clamp(sizing_confidence), 4),
        "creator_link_risk_score": float(evidence_quality["creator_link_risk_score"]),
        "continuation_confidence": evidence_quality["continuation_confidence"],
        "runtime_confidence": evidence_quality["runtime_confidence"],
        "x_status": evidence_quality["x_status"],
    }


def summarize_sizing_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "signal_id": decision.get("signal_id"),
        "token_address": decision.get("token_address"),
        "sizing_origin": decision.get("sizing_origin"),
        "base_position_pct": decision.get("base_position_pct"),
        "effective_position_pct": decision.get("effective_position_pct"),
        "sizing_multiplier": decision.get("sizing_multiplier"),
        "sizing_confidence": decision.get("sizing_confidence"),
        "evidence_quality_score": decision.get("evidence_quality_score"),
        "evidence_conflict_flag": decision.get("evidence_conflict_flag"),
        "partial_evidence_flag": decision.get("partial_evidence_flag"),
        "sizing_reason_codes": decision.get("sizing_reason_codes", []),
        "sizing_warning": decision.get("sizing_warning"),
    }


def compute_evidence_weighted_size(
    signal: Mapping[str, Any],
    *,
    base_position_pct: float,
    config: Mapping[str, Any] | None = None,
    policy_origin: str = "mode_policy_only",
    policy_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    policy = _policy_overrides(config)
    base_position = round(_clamp(float(base_position_pct), 0.0, 1.0), 4)
    reason_codes = _dedupe(list(policy_reason_codes or []))

    confidence = derive_sizing_confidence(signal, config=config)
    warnings = list(confidence["warnings"])
    multiplier = 1.0

    if not bool(policy["enabled"]):
        effective_position = base_position
        reason_codes.append("evidence_weighted_sizing_disabled")
        origin = policy_origin
    else:
        if confidence["partial_evidence_flag"]:
            multiplier *= float(policy["partial_evidence_multiplier"])
            reason_codes.append("partial_evidence_size_reduced")
        if confidence["coverage_ratio"] <= 0.35:
            multiplier *= float(policy["missing_evidence_multiplier"])
            reason_codes.append("missing_evidence_size_reduced")
        if confidence["evidence_conflict_flag"]:
            multiplier *= float(policy["evidence_conflict_multiplier"])
            reason_codes.append("evidence_conflict_size_reduced")
        creator_link_risk_score = float(confidence["creator_link_risk_score"])
        if creator_link_risk_score >= 0.7:
            multiplier *= float(policy["creator_link_risk_multiplier"])
            reason_codes.append("creator_link_risk_size_reduced")
        elif creator_link_risk_score >= 0.5:
            multiplier *= float(policy["moderate_link_risk_multiplier"])
            reason_codes.append("creator_link_risk_moderate_size_reduced")

        continuation_confidence = confidence["continuation_confidence"]
        continuation_status = _safe_str(_first_present(signal, "continuation_status", "continuation_inputs_status")).lower()
        if continuation_confidence is not None and continuation_confidence < 0.45:
            multiplier *= float(policy["low_continuation_multiplier"])
            reason_codes.append("continuation_confidence_low_size_reduced")
        elif continuation_status in {"weak", "degraded"}:
            multiplier *= float(policy["low_continuation_multiplier"])
            reason_codes.append("continuation_support_weak_size_reduced")

        cluster_concentration = _safe_float(_first_present(signal, "cluster_concentration_ratio"))
        bundle_cluster_score = _safe_float(_first_present(signal, "bundle_wallet_clustering_score"))
        if (bundle_cluster_score is not None and bundle_cluster_score < 0.45) or (cluster_concentration is not None and cluster_concentration >= 0.7):
            multiplier *= float(policy["low_cluster_confidence_multiplier"])
            reason_codes.append("cluster_evidence_low_confidence_size_reduced")

        runtime_confidence = confidence["runtime_confidence"]
        if runtime_confidence is not None and runtime_confidence < 0.5:
            multiplier *= float(policy["low_runtime_confidence_multiplier"])
            reason_codes.append("runtime_signal_confidence_low_size_reduced")

        if confidence["evidence_quality_score"] < 0.45:
            multiplier *= float(policy["low_quality_multiplier"])
            reason_codes.append("evidence_quality_low_size_reduced")

        multiplier = round(
            _clamp(
                multiplier,
                float(policy["min_multiplier"]),
                float(policy["max_multiplier"]),
            ),
            4,
        )
        effective_position = round(_clamp(base_position * multiplier), 4)
        if multiplier >= 0.9999 and not any(code.endswith("size_reduced") for code in reason_codes):
            reason_codes.append("evidence_support_preserved_base_size")

        if multiplier < 1.0:
            if confidence["partial_evidence_flag"]:
                origin = "partial_evidence_reduced"
            elif any(code.startswith("creator_link_risk") or code.startswith("evidence_conflict") for code in reason_codes):
                origin = "risk_reduced"
            else:
                origin = "evidence_weighted"
        else:
            origin = "evidence_weighted" if confidence["available_evidence"] else policy_origin
        if policy_origin == "degraded_x_policy" and multiplier >= 0.9999:
            origin = "degraded_x_policy"

    warning_text = "; ".join(_dedupe(warnings)) if warnings else None
    result = {
        "contract_version": "evidence_weighted_sizing.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal.get("signal_id"),
        "token_address": signal.get("token_address"),
        "base_position_pct": base_position,
        "effective_position_pct": effective_position,
        "sizing_multiplier": round(0.0 if base_position <= 0 else effective_position / base_position, 4),
        "sizing_reason_codes": _dedupe(reason_codes),
        "sizing_confidence": confidence["sizing_confidence"],
        "sizing_origin": origin,
        "sizing_warning": warning_text,
        "evidence_quality_score": confidence["evidence_quality_score"],
        "evidence_conflict_flag": confidence["evidence_conflict_flag"],
        "partial_evidence_flag": confidence["partial_evidence_flag"],
        "evidence_coverage_ratio": confidence["coverage_ratio"],
        "evidence_available": confidence["available_evidence"],
        "evidence_scores": confidence["evidence_scores"],
        "policy_origin": policy_origin,
    }
    return result


__all__ = [
    "DEFAULT_SIZING_POLICY",
    "compute_evidence_weighted_size",
    "derive_sizing_confidence",
    "summarize_sizing_decision",
]
