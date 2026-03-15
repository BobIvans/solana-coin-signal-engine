"""Deterministic regime checks for entry selection."""

from __future__ import annotations

from typing import Any

_VOLUME_VELOCITY_SCALP_MIN = 2.0
_DEV_SELL_VERY_LOW = 0.02


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_partial_data(token_ctx: dict[str, Any]) -> bool:
    return (
        str(token_ctx.get("enrichment_status") or "").lower() == "partial"
        or str(token_ctx.get("rug_status") or "").lower() == "partial"
    )


def _mandatory_missing(token_ctx: dict[str, Any]) -> list[str]:
    required = ["token_address", "final_score", "regime_candidate", "rug_score", "rug_verdict"]
    return [field for field in required if token_ctx.get(field) is None]


def should_ignore(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    flags: list[str] = []
    warnings: list[str] = []

    missing = _mandatory_missing(token_ctx)
    if missing and settings.ENTRY_SELECTOR_FAILCLOSED:
        flags.append("entry_failclosed_missing_fields")
        return {
            "ignore": True,
            "reason": "partial_data_failclosed",
            "flags": flags,
            "warnings": warnings,
            "missing_fields": missing,
        }

    if str(token_ctx.get("rug_verdict") or "").upper() == "IGNORE":
        flags.append("hard_rug_override")
        return {
            "ignore": True,
            "reason": "safety_override_ignore",
            "flags": flags,
            "warnings": warnings,
            "missing_fields": missing,
        }

    if str(token_ctx.get("regime_candidate") or "").upper() == "IGNORE":
        return {
            "ignore": True,
            "reason": "insufficient_momentum",
            "flags": flags,
            "warnings": warnings,
            "missing_fields": missing,
        }

    if token_ctx.get("mint_revoked") is False:
        return {
            "ignore": True,
            "reason": "safety_override_ignore",
            "flags": flags,
            "warnings": warnings,
            "missing_fields": missing,
        }

    dev_sell = _to_float(token_ctx.get("dev_sell_pressure_5m"))
    if dev_sell > float(settings.RUG_DEV_SELL_PRESSURE_HARD):
        flags.append("dev_sell_pressure_warn")
        return {
            "ignore": True,
            "reason": "dev_sell_pressure_too_high",
            "flags": flags,
            "warnings": warnings,
            "missing_fields": missing,
        }

    if _is_partial_data(token_ctx) and settings.ENTRY_SELECTOR_FAILCLOSED and missing:
        return {
            "ignore": True,
            "reason": "partial_data_failclosed",
            "flags": [*flags, "entry_failclosed_missing_fields"],
            "warnings": warnings,
            "missing_fields": missing,
        }

    return {"ignore": False, "reason": "", "flags": flags, "warnings": warnings, "missing_fields": missing}


def is_scalp_candidate(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    flags: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    if str(token_ctx.get("regime_candidate") or "").upper() != "ENTRY_CANDIDATE":
        failures.append("regime_not_entry_candidate")

    if _to_float(token_ctx.get("final_score")) < float(settings.ENTRY_SCALP_SCORE_MIN):
        failures.append("final_score_below_scalp_min")

    if _to_int(token_ctx.get("age_sec"), default=10**9) >= int(settings.ENTRY_SCALP_MAX_AGE_SEC):
        failures.append("age_too_high_for_scalp")

    if _to_float(token_ctx.get("rug_score"), default=1.0) >= float(settings.ENTRY_RUG_MAX_SCALP):
        failures.append("rug_score_above_scalp_max")

    if _to_float(token_ctx.get("buy_pressure")) < float(settings.ENTRY_BUY_PRESSURE_MIN_SCALP):
        failures.append("buy_pressure_too_low")

    if _to_float(token_ctx.get("first30s_buy_ratio")) < float(settings.ENTRY_FIRST30S_BUY_RATIO_MIN):
        failures.append("first30s_buy_ratio_too_low")

    if _to_float(token_ctx.get("bundle_cluster_score")) < float(settings.ENTRY_BUNDLE_CLUSTER_MIN):
        failures.append("bundle_cluster_too_low")

    if _to_float(token_ctx.get("volume_velocity")) < _VOLUME_VELOCITY_SCALP_MIN:
        failures.append("volume_velocity_not_strong")

    if _to_float(token_ctx.get("dev_sell_pressure_5m")) > _DEV_SELL_VERY_LOW:
        failures.append("dev_sell_pressure_not_low")

    x_score = _to_float(token_ctx.get("x_validation_score"))
    x_status = str(token_ctx.get("x_status") or "unknown").lower()
    if x_score < float(settings.ENTRY_SCALP_MIN_X_SCORE):
        if x_status == "degraded":
            warnings.append("x_status_degraded")
            flags.append("x_degraded_size_reduced")
        else:
            failures.append("x_validation_too_low")

    if not failures:
        flags.extend(["scalp_momentum_strong", "bundle_cluster_high", "first30s_buy_ratio_strong"])

    return {
        "eligible": not failures,
        "reason": "high_final_score_and_fast_early_momentum",
        "flags": flags,
        "warnings": warnings,
        "failures": failures,
    }


def is_trend_candidate(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    flags: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    if str(token_ctx.get("regime_candidate") or "").upper() != "ENTRY_CANDIDATE":
        failures.append("regime_not_entry_candidate")

    if _to_float(token_ctx.get("final_score")) < float(settings.ENTRY_TREND_SCORE_MIN):
        failures.append("final_score_below_trend_min")

    if _to_float(token_ctx.get("rug_score"), default=1.0) >= float(settings.ENTRY_RUG_MAX_TREND):
        failures.append("rug_score_above_trend_max")

    if _to_int(token_ctx.get("holder_growth_5m")) < int(settings.ENTRY_HOLDER_GROWTH_MIN_TREND):
        failures.append("holder_growth_too_low")

    if _to_int(token_ctx.get("smart_wallet_hits")) < int(settings.ENTRY_SMART_WALLET_HITS_MIN_TREND):
        failures.append("smart_wallet_hits_too_low")

    if _to_float(token_ctx.get("buy_pressure")) < float(settings.ENTRY_BUY_PRESSURE_MIN_TREND):
        failures.append("buy_pressure_too_low")

    if _to_float(token_ctx.get("x_validation_score")) < float(settings.ENTRY_TREND_MIN_X_SCORE):
        failures.append("x_validation_too_low")

    if _to_float(token_ctx.get("x_validation_delta")) <= 0:
        failures.append("x_validation_delta_non_positive")

    if _to_float(token_ctx.get("dev_sell_pressure_5m")) > 0:
        failures.append("dev_sell_pressure_not_zero")

    if token_ctx.get("lp_burn_confirmed") is not True:
        warnings.append("lp_not_burned_warning")

    if str(token_ctx.get("x_status") or "").lower() == "degraded":
        warnings.append("x_status_degraded")
        flags.append("x_degraded_size_reduced")

    if not failures:
        flags.extend(["trend_holder_growth_strong", "trend_smart_wallet_confirmation"])

    return {
        "eligible": not failures,
        "reason": "trend_confirmation_with_holder_growth",
        "flags": flags,
        "warnings": warnings,
        "failures": failures,
    }
