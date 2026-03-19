"""Conservative, evidence-linked config suggestion generator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from config.settings import Settings
from utils.io import read_json, write_json

_ML_FILE_CANDIDATES = ("ml_model_summary.json", "ml_feature_importance.json")
_FEATURE_IMPORTANCE_KEYS = (
    "feature_importance",
    "feature_importances",
    "features",
    "importances",
)

_PARAMETER_SPECS: dict[str, dict[str, Any]] = {
    "ENTRY_TREND_SCORE_MIN": {"attr": "ENTRY_TREND_SCORE_MIN", "kind": "int", "step": 1.0, "min": 0.0, "max": 100.0},
    "ENTRY_TREND_MIN_X_SCORE": {"attr": "ENTRY_TREND_MIN_X_SCORE", "kind": "int", "step": 1.0, "min": 0.0, "max": 100.0},
    "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY": {
        "attr": "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY",
        "kind": "float",
        "step": 0.5,
        "min": 0.0,
    },
    "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX": {
        "attr": "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX",
        "kind": "float",
        "step": 0.5,
        "min": 0.0,
    },
    "UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX": {
        "attr": "UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX",
        "kind": "float",
        "step": 0.5,
        "min": 0.0,
    },
    "UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX": {
        "attr": "UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX",
        "kind": "float",
        "step": 0.5,
        "min": 0.0,
    },
}

_RECOMMENDATION_TARGET_TO_PARAMETER = {
    "creator-linked clusters": "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY",
    "cluster concentration": "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX",
    "retry-heavy bundles": "UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX",
    "sell-heavy bundle exposure": "UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX",
    "SCALP->TREND upgrade path": "ENTRY_TREND_SCORE_MIN",
    "TREND promotion guard": "ENTRY_TREND_MIN_X_SCORE",
    "regime_confidence": "ENTRY_TREND_MIN_X_SCORE",
}

_ML_ALIASES = {
    "creator_cluster_penalty": "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY",
    "creator_in_cluster_flag": "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY",
    "single_cluster_penalty": "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX",
    "cluster_concentration_ratio": "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX",
    "retry_manipulation_penalty": "UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX",
    "bundle_sell_heavy_penalty": "UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX",
    "regime_confidence": "ENTRY_TREND_MIN_X_SCORE",
    "final_score": "ENTRY_TREND_SCORE_MIN",
}


def _candidate_dirs(settings: Settings) -> list[Path]:
    dirs = [
        settings.PROCESSED_DATA_DIR,
        settings.TRADES_DIR,
        settings.SIGNALS_DIR,
        settings.POSITIONS_DIR,
        settings.PROCESSED_DATA_DIR.parent,
        settings.TRADES_DIR.parent,
        settings.SIGNALS_DIR.parent,
        settings.POSITIONS_DIR.parent,
    ]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for directory in dirs:
        if directory in seen:
            continue
        seen.add(directory)
        deduped.append(directory)
    return deduped


def _resolve_optional_json(settings: Settings, filename: str) -> tuple[Path | None, Any]:
    for directory in _candidate_dirs(settings):
        path = directory / filename
        if path.exists():
            return path, read_json(path, default={})
    return None, {}


def _extract_recommendations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    recs = payload.get("recommendations", [])
    return recs if isinstance(recs, list) else []


def _extract_feature_importances(ml_summary: dict[str, Any], ml_feature_importance: dict[str, Any]) -> dict[str, float]:
    raw_sources: list[Any] = []
    for source in (ml_feature_importance, ml_summary):
        if not isinstance(source, dict):
            continue
        raw_sources.append(source)
        for key in _FEATURE_IMPORTANCE_KEYS:
            if key in source:
                raw_sources.append(source.get(key))

    feature_scores: dict[str, float] = {}
    for source in raw_sources:
        if isinstance(source, dict):
            for name, value in source.items():
                try:
                    feature_scores[str(name)] = abs(float(value))
                except (TypeError, ValueError):
                    continue
        elif isinstance(source, list):
            for item in source:
                if not isinstance(item, dict):
                    continue
                name = item.get("feature") or item.get("name") or item.get("metric")
                value = item.get("importance", item.get("gain", item.get("score")))
                if name in {None, ""}:
                    continue
                try:
                    feature_scores[str(name)] = abs(float(value))
                except (TypeError, ValueError):
                    continue
    return feature_scores


def _ml_support_for_parameter(feature_importances: dict[str, float], parameter: str) -> dict[str, Any]:
    relevant = [
        {"feature": feature, "importance": importance}
        for feature, importance in feature_importances.items()
        if _ML_ALIASES.get(feature) == parameter
    ]
    if not relevant:
        return {"supported": False, "top_feature": None, "importance": None}

    ranked = sorted(relevant, key=lambda row: (row["importance"], row["feature"]), reverse=True)
    cutoff = median(feature_importances.values()) if feature_importances else 0.0
    top = ranked[0]
    return {
        "supported": bool(top["importance"] >= cutoff),
        "top_feature": top["feature"],
        "importance": round(float(top["importance"]), 6),
    }


def _recommendation_support_map(recommendations_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    support: dict[str, list[dict[str, Any]]] = {}
    for rec in _extract_recommendations(recommendations_payload):
        parameter = _RECOMMENDATION_TARGET_TO_PARAMETER.get(str(rec.get("target")))
        if parameter:
            support.setdefault(parameter, []).append(rec)
    return support


def _current_value(settings: Settings, parameter: str) -> float | int | None:
    spec = _PARAMETER_SPECS.get(parameter)
    if not spec:
        return None
    return getattr(settings, spec["attr"], None)


def _suggest_value(parameter: str, current_value: float | int | None, direction: str, *, magnitude: float = 1.0) -> float | int | None:
    if current_value is None:
        return None
    spec = _PARAMETER_SPECS[parameter]
    delta = float(spec["step"]) * magnitude
    suggested = float(current_value) + delta if direction == "increase" else float(current_value) - delta
    suggested = max(float(spec.get("min", suggested)), suggested)
    if "max" in spec:
        suggested = min(float(spec["max"]), suggested)
    if spec["kind"] == "int":
        return int(round(suggested))
    return round(suggested, 4)


def _confidence(sample_size: int, effect_size: float, consistency: float) -> float:
    sample_factor = min(1.0, sample_size / 20.0)
    effect_factor = min(1.0, abs(effect_size) / 6.0)
    bounded_consistency = max(0.0, min(1.0, consistency))
    value = 0.25 + (0.30 * sample_factor) + (0.25 * effect_factor) + (0.20 * bounded_consistency)
    return round(min(0.9, value), 4)


def _base_payload(settings: Settings, summary: dict[str, Any], matrix_rows: list[dict[str, Any]], ml_summary_path: Path | None) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "contract_version": settings.CONFIG_SUGGESTIONS_CONTRACT_VERSION,
        "inputs": {
            "post_run_summary_available": bool(summary),
            "matrix_available": bool(summary.get("matrix_analysis_available", False) or matrix_rows),
            "ml_summary_available": ml_summary_path is not None,
            "closed_positions": int(summary.get("total_positions_closed", 0)),
        },
        "training_wheels_mode": bool(settings.CONFIG_SUGGESTIONS_TRAINING_WHEELS_MODE),
        "suggestions": [],
        "warnings": [],
    }


def _build_suggestion(
    *,
    settings: Settings,
    parameter: str,
    direction: str,
    reason: str,
    evidence: dict[str, Any],
    sample_size: int,
    effect_size: float,
    recommendation_support: list[dict[str, Any]] | None = None,
    ml_support: dict[str, Any] | None = None,
    numeric_change_allowed: bool = True,
) -> dict[str, Any]:
    current_value = _current_value(settings, parameter)
    support_count = len(recommendation_support or [])
    ml_supported = bool((ml_support or {}).get("supported"))
    consistency = 0.45 + min(0.35, support_count * 0.15) + (0.20 if ml_supported else 0.0)
    confidence = _confidence(sample_size, effect_size, consistency)

    suggestion_type = "monitor_only"
    suggested_value = None
    if numeric_change_allowed and sample_size >= settings.CONFIG_SUGGESTIONS_MIN_SAMPLE and confidence >= 0.6:
        suggestion_type = "tighten_threshold" if direction == "increase" else "loosen_threshold"
        if "PENALTY" in parameter or "BONUS" in parameter:
            suggestion_type = "increase_penalty_cap" if direction == "increase" else "reduce_penalty_cap"
        suggested_value = _suggest_value(parameter, current_value, direction)

    if suggested_value == current_value:
        suggested_value = None
        suggestion_type = "monitor_only"

    return {
        "parameter": parameter,
        "current_value": current_value,
        "suggested_value": suggested_value,
        "direction": direction,
        "confidence": confidence,
        "reason": reason,
        "evidence": {
            **evidence,
            "sample_size": sample_size,
            "effect_size": round(float(effect_size), 4),
            "supporting_recommendations": [
                {
                    "target": rec.get("target"),
                    "suggested_action": rec.get("suggested_action"),
                    "confidence": rec.get("confidence"),
                }
                for rec in (recommendation_support or [])
            ],
            "ml_support": ml_support or {"supported": False},
        },
        "apply_mode": "manual_only",
        "suggestion_type": suggestion_type,
    }


def generate_config_suggestions(
    *,
    summary: dict[str, Any],
    recommendations_payload: dict[str, Any],
    matrix_rows: list[dict[str, Any]],
    ml_summary: dict[str, Any],
    ml_feature_importance: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    ml_summary_path, _ = _resolve_optional_json(settings, "ml_model_summary.json")
    payload = _base_payload(settings, summary, matrix_rows, ml_summary_path)
    warnings: list[str] = payload["warnings"]
    suggestions: list[dict[str, Any]] = payload["suggestions"]

    if not settings.CONFIG_SUGGESTIONS_ENABLED:
        warnings.append("config_suggestions_disabled")
        return payload

    min_sample = int(settings.CONFIG_SUGGESTIONS_MIN_SAMPLE)
    total_closed = int(summary.get("total_positions_closed", 0))
    if total_closed < min_sample:
        warnings.append("insufficient_closed_positions_for_numeric_suggestions")
        suggestions.append(
            {
                "parameter": "global_analysis",
                "current_value": None,
                "suggested_value": None,
                "direction": "hold",
                "confidence": 1.0,
                "reason": "Closed-position sample is below the minimum threshold for safe numeric suggestions.",
                "evidence": {"closed_positions": total_closed, "required_min_sample": min_sample},
                "apply_mode": "manual_only",
                "suggestion_type": "collect_more_data_first",
            }
        )

    if not summary.get("matrix_analysis_available"):
        warnings.append("matrix_artifact_missing_or_unusable")
    if not ml_feature_importance and not ml_summary:
        warnings.append("ml_artifacts_missing")

    feature_importances = _extract_feature_importances(ml_summary, ml_feature_importance)
    rec_support = _recommendation_support_map(recommendations_payload)
    pattern_slices = summary.get("pattern_expectancy_slices", {})

    creator_true = pattern_slices.get("creator_in_cluster_flag:true", {})
    creator_false = pattern_slices.get("creator_in_cluster_flag:false", {})
    creator_effect = float(creator_false.get("avg_net_pnl_pct", 0.0)) - float(creator_true.get("avg_net_pnl_pct", 0.0))
    creator_count = int(creator_true.get("count", 0))
    if creator_count:
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY",
                direction="increase",
                reason="Creator-linked cluster trades underperformed the non-creator slice, so stronger pre-entry penalty is safer than automatic config changes.",
                evidence={
                    "slice": "creator_in_cluster_flag:true",
                    "slice_avg_net_pnl_pct": creator_true.get("avg_net_pnl_pct", 0.0),
                    "comparison_slice": "creator_in_cluster_flag:false",
                    "comparison_avg_net_pnl_pct": creator_false.get("avg_net_pnl_pct", 0.0),
                },
                sample_size=creator_count,
                effect_size=creator_effect,
                recommendation_support=rec_support.get("UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY"),
                ml_support=_ml_support_for_parameter(feature_importances, "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY"),
                numeric_change_allowed=creator_count >= min_sample and creator_effect >= 2.0 and float(creator_true.get("avg_net_pnl_pct", 0.0)) < 0.0,
            )
        )

    concentration_high = pattern_slices.get("cluster_concentration_ratio:gte_0.6", {})
    concentration_low = pattern_slices.get("cluster_concentration_ratio:lt_0.6", {})
    concentration_effect = float(concentration_low.get("avg_net_pnl_pct", 0.0)) - float(concentration_high.get("avg_net_pnl_pct", 0.0))
    concentration_count = int(concentration_high.get("count", 0))
    if concentration_count:
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX",
                direction="increase",
                reason="High cluster concentration showed weaker realized expectancy than lower-concentration trades, so any change should start as a modest penalty-cap review.",
                evidence={
                    "slice": "cluster_concentration_ratio:gte_0.6",
                    "slice_avg_net_pnl_pct": concentration_high.get("avg_net_pnl_pct", 0.0),
                    "comparison_slice": "cluster_concentration_ratio:lt_0.6",
                    "comparison_avg_net_pnl_pct": concentration_low.get("avg_net_pnl_pct", 0.0),
                },
                sample_size=concentration_count,
                effect_size=concentration_effect,
                recommendation_support=rec_support.get("UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX"),
                ml_support=_ml_support_for_parameter(feature_importances, "UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX"),
                numeric_change_allowed=concentration_count >= min_sample
                and concentration_effect >= 2.0
                and float(concentration_high.get("avg_net_pnl_pct", 0.0)) < 0.0,
            )
        )

    retry_high = pattern_slices.get("retry_manipulation_penalty:gte_0.5", {})
    retry_low = pattern_slices.get("retry_manipulation_penalty:lt_0.5", {})
    retry_effect = float(retry_low.get("avg_net_pnl_pct", 0.0)) - float(retry_high.get("avg_net_pnl_pct", 0.0))
    retry_count = int(retry_high.get("count", 0))
    if retry_count:
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX",
                direction="increase",
                reason="Retry-heavy bundle patterns underperformed cleaner flows, so only a manual penalty-cap review is suggested.",
                evidence={
                    "slice": "retry_manipulation_penalty:gte_0.5",
                    "slice_avg_net_pnl_pct": retry_high.get("avg_net_pnl_pct", 0.0),
                    "comparison_slice": "retry_manipulation_penalty:lt_0.5",
                    "comparison_avg_net_pnl_pct": retry_low.get("avg_net_pnl_pct", 0.0),
                },
                sample_size=retry_count,
                effect_size=retry_effect,
                recommendation_support=rec_support.get("UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX"),
                ml_support=_ml_support_for_parameter(feature_importances, "UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX"),
                numeric_change_allowed=retry_count >= min_sample and retry_effect >= 2.0 and float(retry_high.get("avg_net_pnl_pct", 0.0)) < 0.0,
            )
        )

    sell_heavy_high = pattern_slices.get("bundle_sell_heavy_penalty:gte_0.5", {})
    sell_heavy_low = pattern_slices.get("bundle_sell_heavy_penalty:lt_0.5", {})
    sell_heavy_effect = float(sell_heavy_low.get("avg_net_pnl_pct", 0.0)) - float(sell_heavy_high.get("avg_net_pnl_pct", 0.0))
    sell_heavy_count = int(sell_heavy_high.get("count", 0))
    if sell_heavy_count:
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX",
                direction="increase",
                reason="Sell-heavy bundles lagged cleaner bundle composition, which supports at most a small manual penalty-cap increase when evidence is strong.",
                evidence={
                    "slice": "bundle_sell_heavy_penalty:gte_0.5",
                    "slice_avg_net_pnl_pct": sell_heavy_high.get("avg_net_pnl_pct", 0.0),
                    "comparison_slice": "bundle_sell_heavy_penalty:lt_0.5",
                    "comparison_avg_net_pnl_pct": sell_heavy_low.get("avg_net_pnl_pct", 0.0),
                },
                sample_size=sell_heavy_count,
                effect_size=sell_heavy_effect,
                recommendation_support=rec_support.get("UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX"),
                ml_support=_ml_support_for_parameter(feature_importances, "UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX"),
                numeric_change_allowed=sell_heavy_count >= min_sample
                and sell_heavy_effect >= 2.0
                and float(sell_heavy_high.get("avg_net_pnl_pct", 0.0)) < 0.0,
            )
        )

    trend_failure = summary.get("trend_failure_summary", {})
    trend_failure_count = int(trend_failure.get("count", 0))
    high_conf_bucket = summary.get("regime_confusion_summary", {}).get("regime_confidence_buckets", {}).get("regime_confidence:gte_0.7", {})
    low_conf_bucket = summary.get("regime_confusion_summary", {}).get("regime_confidence_buckets", {}).get("regime_confidence:lt_0.7", {})
    confidence_gap = float(high_conf_bucket.get("avg_net_pnl_pct", 0.0)) - float(low_conf_bucket.get("avg_net_pnl_pct", 0.0))
    trend_effect = abs(float(trend_failure.get("avg_net_pnl_pct", 0.0))) + max(0.0, confidence_gap)
    if trend_failure_count:
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="ENTRY_TREND_MIN_X_SCORE",
                direction="increase",
                reason="TREND trades failed fast often enough that the confidence floor looks safer as a manual review candidate than an automatic rule change.",
                evidence={
                    "trend_failed_fast_count": trend_failure_count,
                    "trend_failed_fast_avg_net_pnl_pct": trend_failure.get("avg_net_pnl_pct", 0.0),
                    "high_confidence_avg_net_pnl_pct": high_conf_bucket.get("avg_net_pnl_pct", 0.0),
                    "low_confidence_avg_net_pnl_pct": low_conf_bucket.get("avg_net_pnl_pct", 0.0),
                },
                sample_size=trend_failure_count,
                effect_size=trend_effect,
                recommendation_support=rec_support.get("ENTRY_TREND_MIN_X_SCORE"),
                ml_support=_ml_support_for_parameter(feature_importances, "ENTRY_TREND_MIN_X_SCORE"),
                numeric_change_allowed=trend_failure_count >= min_sample and float(trend_failure.get("avg_net_pnl_pct", 0.0)) <= -3.0,
            )
        )

    scalp_missed = summary.get("scalp_missed_trend_summary", {})
    scalp_missed_count = int(scalp_missed.get("count", 0))
    scalp_gap = float(scalp_missed.get("avg_mfe_capture_gap_pct", 0.0))
    if scalp_missed_count:
        trend_fail_drag = abs(float(trend_failure.get("avg_net_pnl_pct", 0.0))) if trend_failure_count else 0.0
        numeric_change_allowed = scalp_missed_count >= min_sample and scalp_gap >= 10.0 and trend_fail_drag < scalp_gap
        suggestions.append(
            _build_suggestion(
                settings=settings,
                parameter="ENTRY_TREND_SCORE_MIN",
                direction="decrease",
                reason="Some SCALP trades showed trend-like continuation, but this should stay manual-only unless the continuation gap persists with a healthy sample.",
                evidence={
                    "scalp_missed_trend_count": scalp_missed_count,
                    "avg_mfe_capture_gap_pct": scalp_gap,
                    "supporting_evidence_count": scalp_missed.get("supporting_evidence_count", 0),
                    "trend_failed_fast_count": trend_failure_count,
                },
                sample_size=scalp_missed_count,
                effect_size=scalp_gap - trend_fail_drag,
                recommendation_support=rec_support.get("ENTRY_TREND_SCORE_MIN"),
                ml_support=_ml_support_for_parameter(feature_importances, "ENTRY_TREND_SCORE_MIN"),
                numeric_change_allowed=numeric_change_allowed,
            )
        )

    suggestions.sort(key=lambda row: (float(row.get("confidence", 0.0)), str(row.get("parameter", ""))), reverse=True)
    return payload


def build_config_suggestions_payload(
    *,
    settings: Settings,
    summary: dict[str, Any] | None = None,
    recommendations_payload: dict[str, Any] | None = None,
    matrix_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary_payload = summary if isinstance(summary, dict) else read_json(settings.PROCESSED_DATA_DIR / "post_run_summary.json", default={})
    recommendations = (
        recommendations_payload
        if isinstance(recommendations_payload, dict)
        else read_json(settings.PROCESSED_DATA_DIR / "post_run_recommendations.json", default={})
    )
    matrix = matrix_rows or []
    ml_summary_path, ml_summary = _resolve_optional_json(settings, "ml_model_summary.json")
    ml_feature_path, ml_feature_importance = _resolve_optional_json(settings, "ml_feature_importance.json")

    payload = generate_config_suggestions(
        summary=summary_payload,
        recommendations_payload=recommendations,
        matrix_rows=matrix,
        ml_summary=ml_summary if isinstance(ml_summary, dict) else {},
        ml_feature_importance=ml_feature_importance if isinstance(ml_feature_importance, dict) else {},
        settings=settings,
    )
    payload["inputs"]["ml_summary_available"] = ml_summary_path is not None
    payload["inputs"]["ml_feature_importance_available"] = ml_feature_path is not None
    return payload


def write_config_suggestions(
    *,
    settings: Settings,
    summary: dict[str, Any] | None = None,
    recommendations_payload: dict[str, Any] | None = None,
    matrix_rows: list[dict[str, Any]] | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = build_config_suggestions_payload(
        settings=settings,
        summary=summary,
        recommendations_payload=recommendations_payload,
        matrix_rows=matrix_rows,
    )
    target = output_path or (settings.PROCESSED_DATA_DIR / "config_suggestions.json")
    return write_json(target, payload)
