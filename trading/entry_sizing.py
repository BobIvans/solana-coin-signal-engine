"""Entry confidence and paper position sizing."""

from __future__ import annotations

from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
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

    confidence = (
        0.34 * score_strength
        + 0.22 * momentum_strength
        + 0.18 * x_strength
        + 0.16 * safety_strength
        + 0.10 * data_quality_strength
    )
    return round(_clamp(confidence), 4)


def compute_recommended_position_pct(token_ctx: dict[str, Any], decision_ctx: dict[str, Any], settings: Any) -> float:
    mandatory = ["token_address", "final_score", "regime_candidate", "rug_score", "rug_verdict"]
    missing = [field for field in mandatory if token_ctx.get(field) is None]

    if decision_ctx.get("entry_decision") == "IGNORE":
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

    decision = str(decision_ctx.get("entry_decision") or "IGNORE")
    if decision == "SCALP":
        size = min(size, 0.75)
    elif decision == "TREND":
        size = min(size, 1.0)

    return round(_clamp(size), 4)
