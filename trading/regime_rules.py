"""Deterministic regime checks for entry selection."""

from __future__ import annotations

from typing import Any

_VOLUME_VELOCITY_SCALP_MIN = 2.0
_DEV_SELL_VERY_LOW = 0.02
_SCALP_FAST_TIMING_MAX_MIN = 0.35
_TREND_ACCUMULATION_TIMING_MIN = 0.5
_TREND_RETRY_PATTERN_MAX = 3
_TREND_SUCCESS_RATE_MIN = 0.35


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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default)


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


def _assess_trend_evidence(token_ctx: dict[str, Any], settings: Any, trend: dict[str, Any]) -> dict[str, Any]:
    reason_flags = list(trend.get("flags", []))
    warnings = list(trend.get("warnings", []))
    blockers = list(trend.get("failures", []))
    support_points = 0.0
    available_optional = 0
    missing_optional = 0

    if trend.get("eligible"):
        support_points += 2.0
        reason_flags.append("trend_legacy_gate_passed")

    final_score = _to_float(token_ctx.get("final_score"))
    trend_min = float(settings.ENTRY_TREND_SCORE_MIN)
    if final_score >= trend_min + 4:
        support_points += 1.0
        reason_flags.append("trend_final_score_strong")

    holder_growth = token_ctx.get("holder_growth_5m")
    if holder_growth is None:
        missing_optional += 1
    else:
        available_optional += 1
        if _to_int(holder_growth) >= int(settings.ENTRY_HOLDER_GROWTH_MIN_TREND) + 5:
            support_points += 1.0
            reason_flags.append("trend_holder_growth_strong")

    smart_wallet_hits = token_ctx.get("smart_wallet_hits")
    if smart_wallet_hits is None:
        missing_optional += 1
    else:
        available_optional += 1
        if _to_int(smart_wallet_hits) >= int(settings.ENTRY_SMART_WALLET_HITS_MIN_TREND):
            support_points += 1.0
            reason_flags.append("trend_smart_wallet_confirmation")

    x_score = token_ctx.get("x_validation_score")
    if x_score is None:
        missing_optional += 1
    else:
        available_optional += 1
        if _to_float(x_score) >= float(settings.ENTRY_TREND_MIN_X_SCORE):
            support_points += 1.0
            reason_flags.append("trend_x_validation_strong")

    x_delta = token_ctx.get("x_validation_delta")
    if x_delta is None:
        missing_optional += 1
    else:
        available_optional += 1
        if _to_float(x_delta) > 0:
            support_points += 0.75
            reason_flags.append("trend_x_validation_improving")

    multi_cluster_min = int(_setting(settings, "ENTRY_TREND_MULTI_CLUSTER_MIN", 3))
    clusters = token_ctx.get("num_unique_clusters_first_60s")
    cluster_field_missing = clusters is None
    concentration_field_missing = token_ctx.get("cluster_concentration_ratio") is None
    creator_field_missing = token_ctx.get("creator_in_cluster_flag") is None
    if clusters is None:
        missing_optional += 1
        warnings.append("trend_multi_cluster_evidence_missing")
    else:
        available_optional += 1
        if _to_int(clusters) >= multi_cluster_min:
            support_points += 1.0
            reason_flags.append("trend_multi_cluster_confirmation")
        else:
            blockers.append("trend_multi_cluster_confirmation_missing")

    concentration_max = float(_setting(settings, "ENTRY_TREND_CLUSTER_CONCENTRATION_MAX", 0.55))
    concentration = token_ctx.get("cluster_concentration_ratio")
    if concentration is None:
        missing_optional += 1
        warnings.append("trend_cluster_concentration_missing")
    else:
        available_optional += 1
        if _to_float(concentration) <= concentration_max:
            support_points += 0.75
            reason_flags.append("trend_cluster_distribution_healthy")
        else:
            blockers.append("trend_cluster_concentration_high")

    composition = token_ctx.get("bundle_composition_dominant")
    if composition is None:
        missing_optional += 1
    else:
        available_optional += 1
        composition_value = str(composition).lower()
        if composition_value == "buy-only":
            support_points += 0.75
            reason_flags.append("trend_bundle_buy_only")
        elif composition_value == "sell-only":
            blockers.append("trend_bundle_sell_only")

    timing = token_ctx.get("bundle_timing_from_liquidity_add_min")
    if timing is None:
        missing_optional += 1
        warnings.append("trend_bundle_timing_missing")
    else:
        available_optional += 1
        timing_value = _to_float(timing)
        if timing_value >= _TREND_ACCUMULATION_TIMING_MIN:
            support_points += 0.5
            reason_flags.append("trend_bundle_timing_supports_accumulation")
        elif timing_value < 0.15:
            blockers.append("trend_bundle_timing_too_instant")

    dev_sell_limit = float(_setting(settings, "ENTRY_TREND_DEV_SELL_MAX", _DEV_SELL_VERY_LOW))
    dev_sell = token_ctx.get("dev_sell_pressure_5m")
    if dev_sell is None:
        missing_optional += 1
    else:
        available_optional += 1
        if _to_float(dev_sell) <= dev_sell_limit:
            support_points += 0.75
            reason_flags.append("trend_dev_sell_pressure_safe")
        else:
            blockers.append("trend_dev_sell_pressure_too_high")

    if token_ctx.get("creator_in_cluster_flag") is True:
        blockers.append("trend_creator_cluster_linked")
    elif token_ctx.get("creator_in_cluster_flag") is False:
        support_points += 0.5
        reason_flags.append("trend_creator_not_cluster_linked")
    else:
        warnings.append("trend_creator_cluster_evidence_missing")

    retry_pattern = token_ctx.get("bundle_failure_retry_pattern")
    if retry_pattern is not None:
        available_optional += 1
        if _to_int(retry_pattern) >= _TREND_RETRY_PATTERN_MAX:
            blockers.append("trend_bundle_retry_pattern_severe")
    else:
        missing_optional += 1

    success_rate = token_ctx.get("bundle_success_rate")
    if success_rate is not None:
        available_optional += 1
        if _to_float(success_rate) < _TREND_SUCCESS_RATE_MIN:
            blockers.append("trend_bundle_success_rate_weak")
    else:
        missing_optional += 1

    if str(token_ctx.get("x_status") or "unknown").lower() == "degraded":
        warnings.append("x_status_degraded")
        if _to_float(token_ctx.get("x_validation_score")) < float(settings.ENTRY_TREND_MIN_X_SCORE):
            blockers.append("trend_x_degraded_without_confirmation")

    missing_cluster_fields = int(cluster_field_missing) + int(concentration_field_missing) + int(creator_field_missing)
    if missing_cluster_fields >= 2:
        blockers.append("trend_bundle_cluster_evidence_incomplete")

    if token_ctx.get("lp_burn_confirmed") is True:
        support_points += 0.25
        reason_flags.append("trend_lp_burn_confirmed")
    elif token_ctx.get("lp_burn_confirmed") is False:
        warnings.append("lp_not_burned_warning")

    blocker_penalty = 0.12 * len(set(blockers))
    missing_penalty = 0.03 * missing_optional
    confidence = _clamp(0.18 + (0.085 * support_points) - blocker_penalty - missing_penalty)

    return {
        "reason_flags": _dedupe(reason_flags),
        "warnings": _dedupe(warnings),
        "blockers": _dedupe(blockers),
        "confidence": round(confidence, 4),
        "support_points": round(support_points, 4),
        "available_optional": available_optional,
        "missing_optional": missing_optional,
    }


def _assess_scalp_evidence(token_ctx: dict[str, Any], settings: Any, scalp: dict[str, Any], trend_blockers: list[str]) -> dict[str, Any]:
    reason_flags = list(scalp.get("flags", []))
    warnings = list(scalp.get("warnings", []))
    blockers = list(scalp.get("failures", []))
    support_points = 0.0
    missing_optional = 0

    if scalp.get("eligible"):
        support_points += 2.0
        reason_flags.append("scalp_legacy_gate_passed")

    age_sec = token_ctx.get("age_sec")
    if age_sec is None:
        missing_optional += 1
    else:
        age_value = _to_int(age_sec, default=10**9)
        if age_value <= min(120, int(settings.ENTRY_SCALP_MAX_AGE_SEC)):
            support_points += 1.0
            reason_flags.append("scalp_very_early_window")

    if _to_float(token_ctx.get("volume_velocity")) >= _VOLUME_VELOCITY_SCALP_MIN:
        support_points += 1.0
        reason_flags.append("scalp_volume_velocity_strong")
    elif token_ctx.get("volume_velocity") is None:
        missing_optional += 1

    if _to_float(token_ctx.get("first30s_buy_ratio")) >= float(settings.ENTRY_FIRST30S_BUY_RATIO_MIN):
        support_points += 1.0
        reason_flags.append("scalp_first30s_buy_ratio_strong")
    elif token_ctx.get("first30s_buy_ratio") is None:
        missing_optional += 1

    scalp_bundle_min = int(_setting(settings, "ENTRY_SCALP_BUNDLE_COUNT_MIN", 2))
    bundle_count = token_ctx.get("bundle_count_first_60s")
    if bundle_count is None:
        missing_optional += 1
        warnings.append("scalp_bundle_count_missing")
    else:
        if _to_int(bundle_count) >= scalp_bundle_min:
            support_points += 0.75
            reason_flags.append("scalp_bundle_count_strong")

    timing = token_ctx.get("bundle_timing_from_liquidity_add_min")
    if timing is None:
        missing_optional += 1
    else:
        timing_value = _to_float(timing)
        if timing_value <= _SCALP_FAST_TIMING_MAX_MIN:
            support_points += 0.75
            reason_flags.append("scalp_fast_bundle_timing")

    clustering_score = token_ctx.get("bundle_wallet_clustering_score")
    if clustering_score is None:
        missing_optional += 1
    else:
        if _to_float(clustering_score) >= 0.65:
            support_points += 0.5
            reason_flags.append("scalp_bundle_wallet_clustering_high")

    concentration = token_ctx.get("cluster_concentration_ratio")
    if concentration is None:
        missing_optional += 1
    else:
        if _to_float(concentration) >= float(_setting(settings, "ENTRY_TREND_CLUSTER_CONCENTRATION_MAX", 0.55)):
            support_points += 0.5
            reason_flags.append("scalp_cluster_crowding_high")

    x_score = _to_float(token_ctx.get("x_validation_score"), default=-1.0)
    x_status = str(token_ctx.get("x_status") or "unknown").lower()
    if token_ctx.get("x_validation_score") is None:
        missing_optional += 1
    elif x_score >= float(settings.ENTRY_SCALP_MIN_X_SCORE):
        support_points += 0.5
        reason_flags.append("scalp_x_validation_adequate")
    elif x_status == "degraded":
        support_points += 0.25
        reason_flags.append("scalp_x_degraded_safe")
        warnings.append("x_status_degraded")

    if trend_blockers:
        support_points += 0.5
        reason_flags.append("trend_confirmation_incomplete")

    if token_ctx.get("creator_in_cluster_flag") is True:
        reason_flags.append("creator_cluster_risk_present")

    blocker_penalty = 0.10 * len(set(blockers))
    missing_penalty = 0.02 * missing_optional
    confidence = _clamp(0.20 + (0.09 * support_points) - blocker_penalty - missing_penalty)

    return {
        "reason_flags": _dedupe(reason_flags),
        "warnings": _dedupe(warnings),
        "blockers": _dedupe(blockers),
        "confidence": round(confidence, 4),
        "support_points": round(support_points, 4),
        "missing_optional": missing_optional,
    }


def decide_regime(token_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    ignore = should_ignore(token_ctx, settings)
    trend = is_trend_candidate(token_ctx, settings)
    scalp = is_scalp_candidate(token_ctx, settings)

    if ignore.get("ignore"):
        blockers = [*ignore.get("flags", [])]
        return {
            "regime_decision": "IGNORE",
            "regime_confidence": 0.0,
            "regime_reason_flags": _dedupe(ignore.get("flags", [])),
            "regime_blockers": _dedupe(blockers),
            "expected_hold_class": "none",
            "warnings": _dedupe(ignore.get("warnings", [])),
            "reason": ignore.get("reason") or "insufficient_momentum",
            "trend": trend,
            "scalp": scalp,
            "ignore": ignore,
        }

    trend_eval = _assess_trend_evidence(token_ctx, settings, trend)
    scalp_eval = _assess_scalp_evidence(token_ctx, settings, scalp, trend_eval["blockers"])

    trend_floor = float(_setting(settings, "ENTRY_REGIME_CONFIDENCE_FLOOR_TREND", 0.55))
    scalp_floor = float(_setting(settings, "ENTRY_REGIME_CONFIDENCE_FLOOR_SCALP", 0.40))

    if trend.get("eligible") and not trend_eval["blockers"] and trend_eval["confidence"] >= trend_floor:
        hold_class = "long" if trend_eval["confidence"] >= 0.78 else "medium"
        return {
            "regime_decision": "TREND",
            "regime_confidence": trend_eval["confidence"],
            "regime_reason_flags": trend_eval["reason_flags"],
            "regime_blockers": [],
            "expected_hold_class": hold_class,
            "warnings": trend_eval["warnings"],
            "reason": "trend_confirmation_with_bundle_cluster_support",
            "trend": trend,
            "scalp": scalp,
            "ignore": ignore,
        }

    if scalp.get("eligible") and scalp_eval["confidence"] >= scalp_floor:
        blockers = trend_eval["blockers"] if trend.get("eligible") or trend_eval["blockers"] else scalp_eval["blockers"]
        reason = "high_final_score_and_fast_early_momentum"
        if blockers:
            reason = "scalp_selected_trend_unconfirmed"
        return {
            "regime_decision": "SCALP",
            "regime_confidence": scalp_eval["confidence"],
            "regime_reason_flags": scalp_eval["reason_flags"],
            "regime_blockers": _dedupe(blockers),
            "expected_hold_class": "short",
            "warnings": _dedupe([*trend_eval["warnings"], *scalp_eval["warnings"]]),
            "reason": reason,
            "trend": trend,
            "scalp": scalp,
            "ignore": ignore,
        }

    blockers = _dedupe([*trend_eval["blockers"], *scalp_eval["blockers"]])
    warnings = _dedupe([*trend_eval["warnings"], *scalp_eval["warnings"]])
    if str(token_ctx.get("x_status") or "").lower() == "degraded" and "x_status_degraded" not in warnings:
        warnings.append("x_status_degraded")

    if blockers:
        reason = "regime_evidence_conflicted"
    elif not trend.get("eligible") and not scalp.get("eligible"):
        reason = "insufficient_momentum"
    else:
        reason = "regime_confidence_below_floor"

    return {
        "regime_decision": "IGNORE",
        "regime_confidence": 0.0,
        "regime_reason_flags": [],
        "regime_blockers": blockers,
        "expected_hold_class": "none",
        "warnings": warnings,
        "reason": reason,
        "trend": trend,
        "scalp": scalp,
        "ignore": ignore,
    }
