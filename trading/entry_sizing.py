"""Entry confidence and paper position sizing."""

from __future__ import annotations

from typing import Any

from analytics.evidence_weighted_sizing import compute_evidence_weighted_size


_ENTRY_SIZING_FIELDS = (
    "base_position_pct",
    "effective_position_pct",
    "sizing_multiplier",
    "sizing_reason_codes",
    "sizing_confidence",
    "sizing_origin",
    "sizing_warning",
    "evidence_quality_score",
    "evidence_conflict_flag",
    "partial_evidence_flag",
    "evidence_coverage_ratio",
    "evidence_available",
    "evidence_scores",
    "discovery_lag_penalty_applied",
    "discovery_lag_blocked_trend",
    "discovery_lag_size_multiplier",
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalized_score_strength(final_score: float, decision: str, settings: Any) -> float:
    floor = float(settings.ENTRY_SCALP_SCORE_MIN)
    if decision == "TREND":
        floor = float(settings.ENTRY_TREND_SCORE_MIN)
    return _clamp((final_score - floor) / max(1.0, 100.0 - floor))


def _momentum_strength(token_ctx: dict[str, Any]) -> float:
    buy_pressure = _clamp(_to_float(token_ctx.get("buy_pressure")))
    volume_velocity = _clamp(_to_float(token_ctx.get("volume_velocity")) / 10.0)
    first30s_buy_ratio = _clamp(_to_float(token_ctx.get("first30s_buy_ratio")))
    bundle_cluster = _clamp(_to_float(token_ctx.get("bundle_cluster_score")))
    return (buy_pressure + volume_velocity + first30s_buy_ratio + bundle_cluster) / 4.0


def _x_strength(token_ctx: dict[str, Any]) -> float:
    x_score = _clamp(_to_float(token_ctx.get("x_validation_score")) / 100.0)
    x_delta = _clamp((_to_float(token_ctx.get("x_validation_delta")) + 15.0) / 30.0)
    x_status = str(token_ctx.get("x_status") or "unknown").lower()
    status_factor = 1.0
    if x_status == "degraded":
        status_factor = 0.6
    elif x_status in {"missing", "error", "unknown"}:
        status_factor = 0.4
    return _clamp(((x_score * 0.7) + (x_delta * 0.3)) * status_factor)


def _safety_strength(token_ctx: dict[str, Any]) -> float:
    rug_score = _clamp(1.0 - _to_float(token_ctx.get("rug_score"), default=1.0))
    dev_sell = _clamp(1.0 - (_to_float(token_ctx.get("dev_sell_pressure_5m")) / 0.25))
    lp_burn = 1.0 if token_ctx.get("lp_burn_confirmed") is True else 0.6
    mint_revoked = 1.0 if token_ctx.get("mint_revoked") is not False else 0.0
    freeze_revoked = 1.0 if token_ctx.get("freeze_revoked") is not False else 0.4
    return _clamp((rug_score * 0.35) + (dev_sell * 0.25) + (lp_burn * 0.15) + (mint_revoked * 0.15) + (freeze_revoked * 0.10))


def _wallet_strength(token_ctx: dict[str, Any]) -> float:
    features = token_ctx.get("wallet_features") or {}
    hits = _clamp(_to_float(features.get("smart_wallet_hits"), default=_to_float(token_ctx.get("smart_wallet_hits"))) / 5.0)
    tier1 = _clamp(_to_float(features.get("smart_wallet_tier1_hits"), default=_to_float(token_ctx.get("smart_wallet_tier1_hits"))) / 2.0)
    netflow = _clamp((_to_float(features.get("smart_wallet_netflow_bias"), default=_to_float(token_ctx.get("smart_wallet_netflow_bias"))) + 1.0) / 2.0)
    return _clamp((hits * 0.4) + (tier1 * 0.4) + (netflow * 0.2))


def _data_quality_strength(token_ctx: dict[str, Any]) -> float:
    preferred = [
        "age_sec",
        "buy_pressure",
        "volume_velocity",
        "first30s_buy_ratio",
        "bundle_cluster_score",
        "x_validation_score",
        "x_status",
        "holder_growth_5m",
        "smart_wallet_hits",
    ]
    missing = sum(1 for field in preferred if token_ctx.get(field) is None)
    quality = 1.0 - (missing / float(len(preferred)))

    if str(token_ctx.get("x_status") or "").lower() == "degraded":
        quality *= 0.75
    if str(token_ctx.get("enrichment_status") or "").lower() == "partial":
        quality *= 0.8
    if str(token_ctx.get("rug_status") or "").lower() == "partial":
        quality *= 0.8
    return _clamp(quality)


def _discovery_lag_sizing_details(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    status = str(token_ctx.get("discovery_freshness_status") or "").strip().lower()
    lag_sec = _to_int(token_ctx.get("discovery_lag_sec"), 0)
    reduction_sec = _to_int(getattr(settings, "DISCOVERY_LAG_SCALP_SIZE_REDUCTION_SEC", getattr(settings, "DISCOVERY_FIRST_WINDOW_SEC", 60)), 60)
    multiplier = _clamp(_to_float(getattr(settings, "DISCOVERY_LAG_SIZE_MULTIPLIER", 0.6), 0.6), 0.0, 1.0)
    apply_penalty = status == "post_first_window" or (lag_sec > 0 and lag_sec >= reduction_sec)
    return {
        "status": status,
        "lag_sec": lag_sec,
        "penalty_applied": apply_penalty,
        "size_multiplier": multiplier if apply_penalty else 1.0,
    }


def compute_entry_confidence(token_ctx: dict[str, Any], decision_ctx: dict[str, Any], settings: Any) -> float:
    if decision_ctx.get("entry_decision") == "IGNORE":
        return 0.0

    score_strength = _normalized_score_strength(
        _to_float(token_ctx.get("final_score")),
        str(decision_ctx.get("entry_decision") or "IGNORE"),
        settings,
    )
    momentum_strength = _momentum_strength(token_ctx)
    x_strength = _x_strength(token_ctx)
    safety_strength = _safety_strength(token_ctx)
    data_quality_strength = _data_quality_strength(token_ctx)
    wallet_strength = _wallet_strength(token_ctx)

    confidence = (
        0.31 * score_strength
        + 0.22 * momentum_strength
        + 0.16 * x_strength
        + 0.16 * safety_strength
        + 0.10 * data_quality_strength
        + 0.05 * wallet_strength
    )
    return round(_clamp(confidence), 4)


def compute_recommended_position_pct(token_ctx: dict[str, Any], decision_ctx: dict[str, Any], settings: Any) -> float:
    mandatory = ["token_address", "final_score", "regime_candidate", "rug_score", "rug_verdict"]
    missing = [field for field in mandatory if token_ctx.get(field) is None]

    if decision_ctx.get("entry_decision") == "IGNORE":
        decision_ctx["discovery_lag_penalty_applied"] = bool(decision_ctx.get("discovery_lag_penalty_applied", False))
        decision_ctx["discovery_lag_size_multiplier"] = 0.0 if decision_ctx.get("discovery_lag_penalty_applied") else 1.0
        return 0.0
    if str(token_ctx.get("rug_verdict") or "").upper() == "IGNORE":
        return 0.0
    if settings.ENTRY_SELECTOR_FAILCLOSED and missing:
        return 0.0

    size = float(settings.ENTRY_MAX_BASE_POSITION_PCT) * _to_float(decision_ctx.get("entry_confidence"))

    flags = decision_ctx.setdefault("entry_flags", [])

    if str(token_ctx.get("x_status") or "").lower() == "degraded":
        size *= float(settings.ENTRY_DEGRADED_X_SIZE_MULTIPLIER)
        if "x_degraded_size_reduced" not in flags:
            flags.append("x_degraded_size_reduced")

    if str(token_ctx.get("enrichment_status") or "").lower() == "partial" or str(token_ctx.get("rug_status") or "").lower() == "partial":
        size *= float(settings.ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER)
        if "partial_data_size_reduced" not in flags:
            flags.append("partial_data_size_reduced")

    lag_details = _discovery_lag_sizing_details(token_ctx, settings)
    decision_ctx["discovery_lag_penalty_applied"] = bool(decision_ctx.get("discovery_lag_penalty_applied") or lag_details["penalty_applied"])
    decision_ctx["discovery_lag_size_multiplier"] = float(lag_details["size_multiplier"])
    decision_ctx["discovery_lag_blocked_trend"] = bool(decision_ctx.get("discovery_lag_blocked_trend", False))
    if lag_details["penalty_applied"]:
        size *= float(lag_details["size_multiplier"])
        if "discovery_lag_penalty" not in flags:
            flags.append("discovery_lag_penalty")

    decision = str(decision_ctx.get("entry_decision") or "IGNORE")
    if decision == "SCALP":
        size = min(size, 0.75)
    elif decision == "TREND":
        size = min(size, 1.0)

    return round(_clamp(size), 4)


def _zero_entry_position_contract(entry_confidence: float, *, decision_ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = decision_ctx or {}
    return {
        "entry_confidence": round(_clamp(entry_confidence), 4),
        "recommended_position_pct": 0.0,
        "base_position_pct": 0.0,
        "effective_position_pct": 0.0,
        "sizing_multiplier": 0.0,
        "sizing_reason_codes": [],
        "sizing_confidence": 0.0,
        "sizing_origin": "mode_policy_only",
        "sizing_warning": None,
        "evidence_quality_score": 0.0,
        "evidence_conflict_flag": False,
        "partial_evidence_flag": False,
        "evidence_coverage_ratio": 0.0,
        "evidence_available": [],
        "evidence_scores": {},
        "discovery_lag_penalty_applied": bool(ctx.get("discovery_lag_penalty_applied", False)),
        "discovery_lag_blocked_trend": bool(ctx.get("discovery_lag_blocked_trend", False)),
        "discovery_lag_size_multiplier": float(ctx.get("discovery_lag_size_multiplier", 1.0)),
    }


def compute_entry_position_contract(token_ctx: dict[str, Any], decision_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    entry_confidence = compute_entry_confidence(token_ctx, decision_ctx, settings)
    decision_ctx["entry_confidence"] = entry_confidence
    recommended_position_pct = compute_recommended_position_pct(token_ctx, decision_ctx, settings)

    if recommended_position_pct <= 0:
        return _zero_entry_position_contract(entry_confidence, decision_ctx=decision_ctx)

    sizing_input = {
        **token_ctx,
        **decision_ctx,
        "entry_confidence": entry_confidence,
        "runtime_signal_confidence": entry_confidence,
        "recommended_position_pct": recommended_position_pct,
        "token_address": token_ctx.get("token_address"),
        "signal_id": token_ctx.get("signal_id") or token_ctx.get("token_address"),
    }
    sizing = compute_evidence_weighted_size(
        sizing_input,
        base_position_pct=recommended_position_pct,
        config=None,
        policy_origin="entry_base_policy",
        policy_reason_codes=[],
    )
    return {
        "entry_confidence": entry_confidence,
        "recommended_position_pct": recommended_position_pct,
        **{field: sizing.get(field) for field in _ENTRY_SIZING_FIELDS},
    }
