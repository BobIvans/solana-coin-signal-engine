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


def generate_recommendations(
    summary: dict[str, Any], correlations: list[dict[str, Any]], slices: dict[str, Any], settings: Settings
) -> list[dict[str, Any]]:
    min_sample = int(settings.POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION)
    confidence_min = float(settings.POST_RUN_RECOMMENDATION_CONFIDENCE_MIN)

    recommendations: list[dict[str, Any]] = []

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

        if confidence >= confidence_min:
            recommendations.append(
                {
                    "type": "weight_adjustment",
                    "target": _METRIC_TO_WEIGHT_TARGET[metric],
                    "current_direction": "positive",
                    "suggested_action": action,
                    "confidence": round(confidence, 4),
                    "reason": reason,
                }
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

    return recommendations
