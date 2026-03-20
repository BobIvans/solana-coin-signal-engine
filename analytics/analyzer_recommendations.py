"""Conservative recommendation engine for post-run analysis."""

from __future__ import annotations

from typing import Any

from config.settings import Settings


_METRIC_TO_WEIGHT_TARGET = {
    "bundle_cluster_score": "bundle_cluster_score",
    "first30s_buy_ratio": "first30s_buy_ratio",
    "priority_fee_avg_first_min": "priority_fee_avg_first_min",
    "first50_holder_conc_est": "first50_holder_conc_est",
    "holder_entropy_est": "holder_entropy_est",
    "dev_sell_pressure_5m": "dev_sell_pressure_5m",
    "pumpfun_to_raydium_sec": "pumpfun_to_raydium_sec",
    "x_validation_score": "x_validation_score",
}


def _mk_rec(rec_type: str, target: str, action: str, confidence: float, reason: str) -> dict[str, Any]:
    return {
        "type": rec_type,
        "target": target,
        "suggested_action": action,
        "confidence": round(confidence, 4),
        "reason": reason,
    }


def _add_if_confident(recommendations: list[dict[str, Any]], rec: dict[str, Any], confidence_min: float) -> None:
    if float(rec.get("confidence", 0.0)) >= confidence_min:
        recommendations.append(rec)


def generate_recommendations(
    summary: dict[str, Any],
    correlations: list[dict[str, Any]],
    slices: dict[str, Any],
    settings: Settings,
    analyzer_slices: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    min_sample = int(settings.POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION)
    confidence_min = float(settings.POST_RUN_RECOMMENDATION_CONFIDENCE_MIN)

    recommendations: list[dict[str, Any]] = []
    analyzer_slices = analyzer_slices or {}

    total_closed = int(summary.get("total_positions_closed", 0))
    if total_closed < min_sample:
        recommendations.append(
            _mk_rec(
                "sample_size_warning",
                "global",
                "collect_more_data",
                1.0,
                "sample size below recommendation threshold; avoid strong parameter changes",
            )
        )

    for corr in correlations:
        metric = corr.get("metric")
        if metric not in _METRIC_TO_WEIGHT_TARGET:
            continue
        if corr.get("status") != "ok":
            continue
        sample_size = int(corr.get("sample_size", 0))
        if sample_size < min_sample:
            continue
        avg_corr = (float(corr.get("pearson_corr", 0.0)) + float(corr.get("spearman_corr", 0.0))) / 2
        abs_corr = abs(avg_corr)
        if abs_corr < 0.10:
            action = "hold_weight"
            confidence = 0.56
            reason = "near-flat linkage to pnl"
        elif avg_corr > 0:
            action = "increase_weight_medium" if abs_corr >= 0.35 else "increase_weight_small"
            confidence = min(0.9, 0.55 + abs_corr)
            reason = "positive correlation with pnl"
        else:
            action = "decrease_weight_medium" if abs_corr >= 0.35 else "decrease_weight_small"
            confidence = min(0.9, 0.55 + abs_corr)
            reason = "negative correlation with pnl"

        _add_if_confident(
            recommendations,
            {
                "type": "weight_adjustment",
                "target": _METRIC_TO_WEIGHT_TARGET[metric],
                "current_direction": "positive",
                "suggested_action": action,
                "confidence": round(confidence, 4),
                "reason": reason,
            },
            confidence_min,
        )

    regime_metrics = slices.get("regime", {})
    scalp_count = int(regime_metrics.get("SCALP", {}).get("count", 0))
    trend_count = int(regime_metrics.get("TREND", {}).get("count", 0))
    if scalp_count >= min_sample and trend_count >= min_sample:
        scalp_wr = float(regime_metrics.get("SCALP", {}).get("winrate", 0.0))
        trend_wr = float(regime_metrics.get("TREND", {}).get("winrate", 0.0))
        if scalp_wr < trend_wr - 0.10:
            recommendations.append(
                _mk_rec(
                    "threshold_adjustment",
                    "ENTRY_SCALP_SCORE_MIN",
                    "increase_by_2",
                    0.58,
                    "scalp underperforms trend in winrate",
                )
            )

    friction_summary = summary.get("friction_summary", {})
    if float(friction_summary.get("failed_fill_rate", 0.0)) > 0.20:
        recommendations.append(
            _mk_rec(
                "friction_model_adjustment",
                "fill_policy",
                "tighten_entry_size_on_thin_liquidity",
                0.65,
                "high failed fill rate erodes realized edge",
            )
        )

    degraded_slice = slices.get("x_status", {}).get("degraded", {})
    if int(degraded_slice.get("count", 0)) >= min_sample:
        recommendations.append(
            _mk_rec(
                "degrade_policy_adjustment",
                "x_status=degraded",
                "stricter_size_cut",
                0.6,
                "degraded X appears frequently; reduce risk in degraded mode",
            )
        )

    if summary.get("matrix_analysis_available"):
        regime_confusion = summary.get("regime_confusion_summary", {})
        trend_failed = summary.get("trend_failure_summary", {})
        scalp_missed = summary.get("scalp_missed_trend_summary", {})
        scalp_vs_trend_outcomes = summary.get("scalp_vs_trend_outcome_summary", {})
        trend_survival_summary = summary.get("trend_survival_summary", {})
        pattern_slices = summary.get("pattern_expectancy_slices", {})

        if int(trend_failed.get("count", 0)) >= min_sample and float(trend_failed.get("avg_net_pnl_pct", 0.0)) < 0:
            recommendations.append(
                _mk_rec(
                    "matrix_threshold_adjustment",
                    "TREND promotion guard",
                    "raise_trend_confidence_and_breakdown_filters",
                    0.71,
                    "TREND promotions are failing fast with negative expectancy in the feature matrix",
                )
            )

        if int(scalp_missed.get("count", 0)) >= min_sample and float(scalp_missed.get("avg_mfe_capture_gap_pct", 0.0)) >= 8.0:
            recommendations.append(
                _mk_rec(
                    "matrix_threshold_adjustment",
                    "SCALP->TREND upgrade path",
                    "allow_more_trend_follow_through_when_continuation_evidence_is_present",
                    0.69,
                    "SCALP entries left material MFE uncaptured despite trend-like continuation evidence",
                )
            )

        scalp_survival = float(scalp_vs_trend_outcomes.get("SCALP", {}).get("trend_survival_15m", {}).get("avg") or 0.0)
        trend_survival = float(scalp_vs_trend_outcomes.get("TREND", {}).get("trend_survival_15m", {}).get("avg") or 0.0)
        if trend_survival >= 0.0 and scalp_survival >= 0.0 and trend_survival + 0.20 < scalp_survival:
            recommendations.append(
                _mk_rec(
                    "matrix_calibration_observation",
                    "SCALP runners",
                    "review_scalp_exit_capture_for_longer_follow_through",
                    0.62,
                    "SCALP trades are surviving above entry longer than TREND trades in the 15m hindsight window",
                )
            )

        fast_profit_summary = summary.get("time_to_first_profit_summary", {}).get("by_regime", {})
        scalp_fast_profit = float(fast_profit_summary.get("SCALP", {}).get("avg") or 0.0)
        trend_fast_profit = float(fast_profit_summary.get("TREND", {}).get("avg") or 0.0)
        if scalp_fast_profit > 0 and trend_fast_profit > 0 and trend_fast_profit + 30 < scalp_fast_profit:
            recommendations.append(
                _mk_rec(
                    "matrix_calibration_observation",
                    "slow starters",
                    "review_trend-promotion patience versus quick-scalp assumptions",
                    0.58,
                    "TREND trades are reaching first profit materially faster than SCALP trades in hindsight",
                )
            )

        if int(trend_survival_summary.get("trend_survival_60m", {}).get("count", 0)) >= min_sample and float(trend_survival_summary.get("trend_survival_60m", {}).get("avg") or 0.0) < 0.25:
            recommendations.append(
                _mk_rec(
                    "matrix_calibration_observation",
                    "TREND longevity",
                    "review failed promotions that could not hold above entry across the 60m window",
                    0.6,
                    "Long-window trend survival is weak in hindsight, suggesting many promoted trends failed early",
                )
            )

        creator_slice = pattern_slices.get("creator_in_cluster_flag:true", {})
        if int(creator_slice.get("count", 0)) >= min_sample and float(creator_slice.get("avg_net_pnl_pct", 0.0)) < 0:
            recommendations.append(
                _mk_rec(
                    "matrix_risk_adjustment",
                    "creator-linked clusters",
                    "tighten_or_penalize_creator_cluster_exposure",
                    0.74,
                    "creator-linked cluster slice shows negative expectancy in matrix-derived trades",
                )
            )

        concentration_slice = pattern_slices.get("cluster_concentration_ratio:gte_0.6", {})
        if int(concentration_slice.get("count", 0)) >= min_sample and float(concentration_slice.get("avg_net_pnl_pct", 0.0)) < 0:
            recommendations.append(
                _mk_rec(
                    "matrix_risk_adjustment",
                    "cluster concentration",
                    "reduce_size_when_cluster_concentration_is_high",
                    0.72,
                    "high concentration bundles underperform in the trade feature matrix",
                )
            )

        retry_slice = pattern_slices.get("retry_manipulation_penalty:gte_0.5", {})
        if int(retry_slice.get("count", 0)) >= min_sample and float(retry_slice.get("avg_net_pnl_pct", 0.0)) < 0:
            recommendations.append(
                _mk_rec(
                    "matrix_risk_adjustment",
                    "retry-heavy bundles",
                    "increase_penalty_for_retry_manipulation_patterns",
                    0.68,
                    "retry-heavy bundle slice carries negative expectancy",
                )
            )

        sell_heavy_slice = pattern_slices.get("bundle_sell_heavy_penalty:gte_0.5", {})
        if int(sell_heavy_slice.get("count", 0)) >= min_sample and float(sell_heavy_slice.get("avg_net_pnl_pct", 0.0)) < 0:
            recommendations.append(
                _mk_rec(
                    "matrix_risk_adjustment",
                    "sell-heavy bundle exposure",
                    "raise_sell_heavy_penalty",
                    0.66,
                    "sell-heavy bundle slice underperforms on realized net pnl",
                )
            )

        confidence_buckets = regime_confusion.get("regime_confidence_buckets", {})
        high_conf = confidence_buckets.get("regime_confidence:gte_0.7", {})
        low_conf = confidence_buckets.get("regime_confidence:lt_0.7", {})
        if (
            int(high_conf.get("count", 0)) >= min_sample
            and int(low_conf.get("count", 0)) >= min_sample
            and float(high_conf.get("avg_net_pnl_pct", 0.0)) > float(low_conf.get("avg_net_pnl_pct", 0.0)) + 3.0
        ):
            recommendations.append(
                _mk_rec(
                    "matrix_threshold_adjustment",
                    "regime_confidence",
                    "prefer_high_confidence_regime_calls",
                    0.63,
                    "high-confidence regime calls outperform low-confidence calls in matrix slices",
                )
            )

    slice_inputs = analyzer_slices.get("recommendation_inputs", {})
    for item in slice_inputs.get("actionable_slices", []):
        sample_size = int(item.get("sample_size", 0))
        if sample_size < min_sample:
            continue
        confidence_label = str(item.get("confidence", "low"))
        confidence = {"low": 0.56, "medium": 0.64, "high": 0.74}.get(confidence_label, 0.58)
        recommendations.append(
            _mk_rec(
                "slice_manual_review",
                item.get("slice_name", "unknown_slice"),
                "manual_review_only",
                confidence,
                f"{item.get('recommendation_hint')} (sample={sample_size}; manual-only)",
            )
        )

    for slice_name in slice_inputs.get("low_sample_slices", [])[:4]:
        recommendations.append(
            _mk_rec(
                "slice_sample_warning",
                slice_name,
                "observe_only",
                1.0,
                "slice evidence is below the minimum sample threshold; keep conclusions conservative",
            )
        )

    return recommendations
