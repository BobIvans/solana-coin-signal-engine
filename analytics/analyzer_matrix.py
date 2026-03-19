"""Optional matrix-aware analysis helpers for the post-run analyzer."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from analytics.analyzer_correlations import compute_metric_correlations
from config.settings import Settings

_MATRIX_NUMERIC_FIELDS = [
    "regime_confidence",
    "final_score",
    "bundle_aggression_bonus",
    "organic_multi_cluster_bonus",
    "single_cluster_penalty",
    "creator_cluster_penalty",
    "bundle_sell_heavy_penalty",
    "retry_manipulation_penalty",
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
    "bundle_tip_efficiency",
    "cross_block_bundle_correlation",
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "hold_sec",
    "gross_pnl_pct",
    "net_pnl_pct",
    "mfe_pct",
    "mae_pct",
    "x_validation_score_entry",
    "x_validation_delta_entry",
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "smart_wallet_dispersion_score",
    "x_author_velocity_5m",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
]

_MATRIX_CATEGORICAL_FIELDS = [
    "regime_decision",
    "expected_hold_class",
    "bundle_composition_dominant",
    "bundle_failure_retry_pattern",
    "creator_in_cluster_flag",
    "x_status",
    "exit_reason_final",
]

_SHORT_HOLD_THRESHOLD_SEC = 300.0
_TREND_FAIL_PNL_THRESHOLD = 0.0
_SCALP_MISSED_TREND_GAP_PCT = 8.0
_SMALL_SAMPLE_WARNING = 5


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    import json

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if raw:
            rows.append(json.loads(raw))
    return rows


def resolve_trade_feature_matrix_path(settings: Settings) -> Path | None:
    candidate_dirs = [
        settings.TRADES_DIR,
        settings.SIGNALS_DIR,
        settings.POSITIONS_DIR,
        settings.PROCESSED_DATA_DIR,
        settings.TRADES_DIR.parent,
        settings.SIGNALS_DIR.parent,
        settings.POSITIONS_DIR.parent,
        settings.PROCESSED_DATA_DIR.parent,
    ]
    seen: set[Path] = set()
    for directory in candidate_dirs:
        if directory in seen:
            continue
        seen.add(directory)
        candidate = directory / "trade_feature_matrix.jsonl"
        if candidate.exists():
            return candidate
    return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _net_pnl_pct(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("net_pnl_pct"))


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    net_pnls = [value for row in rows if (value := _net_pnl_pct(row)) is not None]
    hold_values = [value for row in rows if (value := _safe_float(row.get("hold_sec"))) is not None]
    wins = [value for value in net_pnls if value > 0]
    return {
        "count": len(rows),
        "sample_size": len(rows),
        "winrate": (len(wins) / len(net_pnls)) if net_pnls else 0.0,
        "avg_net_pnl_pct": statistics.fmean(net_pnls) if net_pnls else 0.0,
        "median_hold_sec": statistics.median(hold_values) if hold_values else 0.0,
        "expectancy_net_pnl_pct": statistics.fmean(net_pnls) if net_pnls else 0.0,
    }


def merge_closed_positions_with_matrix(closed_positions: list[dict[str, Any]], matrix_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not matrix_rows:
        return []

    closed_by_position_id = {
        str(row.get("position_id")): row
        for row in closed_positions
        if row.get("position_id") not in {None, ""}
    }
    merged: list[dict[str, Any]] = []
    for row in matrix_rows:
        position_id = _safe_str(row.get("position_id"))
        linked_position = closed_by_position_id.get(position_id or "")
        if linked_position:
            merged.append({**linked_position, **row, "position_id": position_id or linked_position.get("position_id")})
            continue

        if _net_pnl_pct(row) is None:
            continue
        merged.append(dict(row))
    return merged


def _available_numeric_fields(rows: list[dict[str, Any]]) -> list[str]:
    available: list[str] = []
    for field in _MATRIX_NUMERIC_FIELDS:
        if any(_safe_float(row.get(field)) is not None for row in rows):
            available.append(field)
    return available


def _threshold_key(field: str, label: str) -> str:
    return f"{field}:{label}"


def _threshold_slices(rows: list[dict[str, Any]], field: str, threshold: float) -> dict[str, dict[str, Any]]:
    low = [row for row in rows if (value := _safe_float(row.get(field))) is not None and value < threshold]
    high = [row for row in rows if (value := _safe_float(row.get(field))) is not None and value >= threshold]
    output: dict[str, dict[str, Any]] = {}
    if low:
        output[_threshold_key(field, f"lt_{threshold}")] = _metric_summary(low)
    if high:
        output[_threshold_key(field, f"gte_{threshold}")] = _metric_summary(high)
    return output


def _categorical_slices(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row.get(field)
        if field == "creator_in_cluster_flag":
            bool_value = _safe_bool(value)
            key = "true" if bool_value else ("false" if bool_value is False else None)
        else:
            key = _safe_str(value)
        if key is None:
            continue
        groups.setdefault(key, []).append(row)
    return {f"{field}:{key}": _metric_summary(items) for key, items in sorted(groups.items())}


def _collect_pattern_expectancy_slices(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field in [
        "bundle_composition_dominant",
        "bundle_failure_retry_pattern",
        "creator_in_cluster_flag",
        "regime_decision",
    ]:
        output.update(_categorical_slices(rows, field))

    for field, threshold in [
        ("cluster_concentration_ratio", 0.6),
        ("single_cluster_penalty", 0.5),
        ("creator_cluster_penalty", 0.5),
        ("retry_manipulation_penalty", 0.5),
        ("bundle_sell_heavy_penalty", 0.5),
        ("bundle_tip_efficiency", 0.5),
        ("cross_block_bundle_correlation", 0.5),
        ("regime_confidence", 0.7),
    ]:
        output.update(_threshold_slices(rows, field, threshold))
    return output


def compute_regime_confusion_slices(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trend_rows = [row for row in rows if _safe_str(row.get("regime_decision")) == "TREND"]
    scalp_rows = [row for row in rows if _safe_str(row.get("regime_decision")) == "SCALP"]

    fast_fail_rows = [
        row
        for row in trend_rows
        if (_net_pnl_pct(row) is not None and _net_pnl_pct(row) <= _TREND_FAIL_PNL_THRESHOLD)
        and (
            (_safe_float(row.get("hold_sec")) or 0.0) <= _SHORT_HOLD_THRESHOLD_SEC
            or _safe_str(row.get("exit_reason_final")) in {"breakdown", "risk", "stop_loss", "scalp_stop_loss"}
        )
    ]

    confidence_groups = _collect_pattern_expectancy_slices([row for row in rows if row.get("regime_confidence") is not None])
    confidence_groups = {k: v for k, v in confidence_groups.items() if k.startswith("regime_confidence:")}

    return {
        "trend_promoted_failed_fast": _metric_summary(fast_fail_rows),
        "trend_overall": _metric_summary(trend_rows),
        "scalp_overall": _metric_summary(scalp_rows),
        "regime_confidence_buckets": confidence_groups,
        "warnings": [
            "matrix_regime_small_sample"
            for sample in [len(trend_rows), len(scalp_rows)]
            if 0 < sample < _SMALL_SAMPLE_WARNING
        ],
    }


def compute_trend_failure_slices(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trend_failed_fast = compute_regime_confusion_slices(rows)["trend_promoted_failed_fast"]
    matching_rows = [
        row
        for row in rows
        if _safe_str(row.get("regime_decision")) == "TREND"
        and (_net_pnl_pct(row) is not None and _net_pnl_pct(row) <= _TREND_FAIL_PNL_THRESHOLD)
        and ((_safe_float(row.get("hold_sec")) or 0.0) <= _SHORT_HOLD_THRESHOLD_SEC)
    ]
    return {
        **trend_failed_fast,
        "avg_regime_confidence": statistics.fmean(
            [value for row in matching_rows if (value := _safe_float(row.get("regime_confidence"))) is not None]
        )
        if matching_rows
        else 0.0,
    }


def compute_scalp_missed_trend_slices(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    capture_gaps: list[float] = []
    for row in rows:
        if _safe_str(row.get("regime_decision")) != "SCALP":
            continue
        mfe = _safe_float(row.get("mfe_pct"))
        realized = _net_pnl_pct(row)
        if mfe is None or realized is None:
            continue
        gap = mfe - realized
        if gap < _SCALP_MISSED_TREND_GAP_PCT:
            continue
        supportive = 0
        if (_safe_float(row.get("bundle_aggression_bonus")) or 0.0) > 0:
            supportive += 1
        if (_safe_float(row.get("organic_multi_cluster_bonus")) or 0.0) > 0:
            supportive += 1
        if (_safe_float(row.get("single_cluster_penalty")) or 0.0) < 0.25:
            supportive += 1
        if not (_safe_bool(row.get("creator_in_cluster_flag")) or False):
            supportive += 1
        if supportive < 2:
            continue
        candidates.append(row)
        capture_gaps.append(gap)

    summary = _metric_summary(candidates)
    summary.update(
        {
            "avg_mfe_capture_gap_pct": statistics.fmean(capture_gaps) if capture_gaps else 0.0,
            "supporting_evidence_count": len(candidates),
        }
    )
    return summary


def compute_matrix_analysis(matrix_rows: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    if not matrix_rows:
        return {
            "matrix_analysis_available": False,
            "matrix_row_count": 0,
            "bundle_cluster_correlations": [],
            "regime_confusion_summary": {},
            "trend_failure_summary": {},
            "scalp_missed_trend_summary": {},
            "pattern_expectancy_slices": {},
            "top_positive_feature_slices": [],
            "top_negative_feature_slices": [],
            "warnings": ["trade_feature_matrix_missing_or_unusable"],
        }

    fields = _available_numeric_fields(matrix_rows)
    correlations = compute_metric_correlations(matrix_rows, fields, "net_pnl_pct", settings)
    ok_correlations = [row for row in correlations if row.get("status") == "ok"]
    ranked = sorted(
        ok_correlations,
        key=lambda row: (
            abs((float(row.get("pearson_corr", 0.0)) + float(row.get("spearman_corr", 0.0))) / 2.0),
            str(row.get("metric", "")),
        ),
        reverse=True,
    )

    pattern_slices = _collect_pattern_expectancy_slices(matrix_rows)
    positive_slices = [
        {"slice": key, **value}
        for key, value in sorted(pattern_slices.items(), key=lambda item: (item[1]["avg_net_pnl_pct"], item[0]), reverse=True)
        if value["count"] > 0
    ][:5]
    negative_slices = [
        {"slice": key, **value}
        for key, value in sorted(pattern_slices.items(), key=lambda item: (item[1]["avg_net_pnl_pct"], item[0]))
        if value["count"] > 0
    ][:5]

    warnings: list[str] = []
    if len(matrix_rows) < max(_SMALL_SAMPLE_WARNING, int(settings.POST_RUN_MIN_TRADES_FOR_CORRELATION)):
        warnings.append("matrix_small_sample_warning")
    if not ok_correlations:
        warnings.append("matrix_correlations_insufficient_sample")

    return {
        "matrix_analysis_available": True,
        "matrix_row_count": len(matrix_rows),
        "bundle_cluster_correlations": correlations,
        "regime_confusion_summary": compute_regime_confusion_slices(matrix_rows),
        "trend_failure_summary": compute_trend_failure_slices(matrix_rows),
        "scalp_missed_trend_summary": compute_scalp_missed_trend_slices(matrix_rows),
        "pattern_expectancy_slices": pattern_slices,
        "top_positive_feature_slices": positive_slices,
        "top_negative_feature_slices": negative_slices,
        "warnings": warnings,
    }


def read_trade_feature_matrix(settings: Settings) -> tuple[Path | None, list[dict[str, Any]]]:
    path = resolve_trade_feature_matrix_path(settings)
    if path is None:
        return None, []
    return path, _read_jsonl(path)
