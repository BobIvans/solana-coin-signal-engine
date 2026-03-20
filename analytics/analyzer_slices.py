"""Rich diagnostic slice helpers for the post-run analyzer."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

_ANALYZER_SLICES_CONTRACT_VERSION = "analyzer_slices.v1"
_DEFAULT_MIN_SAMPLE = 5
_MIN_MEANINGFUL_EDGE_PCT = 1.0
_DEGRADED_X_STATUSES = {"degraded", "degraded_x", "degraded-x"}
_HEALTHY_X_STATUSES = {"healthy", "ok", "strong", "validated"}
_PARTIAL_EVIDENCE_STATUSES = {"partial"}
_LOW_CONFIDENCE_LABELS = {"low", "weak"}
_ELEVATED_LINKAGE_RISK_THRESHOLD = 0.55
_LOW_EVIDENCE_CONFIDENCE_THRESHOLD = 0.45


# ---------------------------------------------------------------------------
# Legacy PR-10 helpers kept for additive compatibility.
# ---------------------------------------------------------------------------

def _fmt_bucket(low: float, high: float | None) -> str:
    if high is None:
        return f"{low:.2f}+"
    return f"{low:.2f}-{high:.2f}"


def _legacy_metric_summary(values: list[dict[str, Any]]) -> dict[str, float]:
    size = len(values)
    wins = sum(1 for row in values if float(row.get("net_pnl_sol", 0.0)) > 0)
    avg_pnl = sum(float(row.get("net_pnl_pct", 0.0)) for row in values) / size if size else 0.0
    return {"count": size, "winrate": (wins / size if size else 0.0), "avg_net_pnl_pct": avg_pnl}


def slice_positions(closed_positions: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in closed_positions:
        grouped[str(position.get(key, "unknown"))].append(position)
    return {bucket: _legacy_metric_summary(items) for bucket, items in grouped.items()}


def bucketize_metric(values: list[dict[str, Any]], field: str, buckets: list[tuple[float, float | None]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in values:
        raw = row.get(field)
        if raw is None:
            grouped["unknown"].append(row)
            continue
        value = float(raw)
        assigned = False
        for low, high in buckets:
            if high is None and value >= low:
                grouped[_fmt_bucket(low, high)].append(row)
                assigned = True
                break
            if high is not None and low <= value < high:
                grouped[_fmt_bucket(low, high)].append(row)
                assigned = True
                break
        if not assigned:
            grouped["out_of_range"].append(row)
    return {bucket: _legacy_metric_summary(items) for bucket, items in grouped.items()}


# ---------------------------------------------------------------------------
# Rich analyzer slices.
# ---------------------------------------------------------------------------

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
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _coalesce(row: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        if field in row and row.get(field) not in (None, ""):
            return row.get(field)
    return None


def _net_pnl_pct(row: dict[str, Any]) -> float | None:
    return _safe_float(_coalesce(row, "net_pnl_pct", "pnl_pct"))


def _exit_reason(row: dict[str, Any]) -> str | None:
    return _safe_str(_coalesce(row, "exit_reason_final", "exit_reason", "first_exit_reason"))


def _regime(row: dict[str, Any]) -> str | None:
    return _safe_str(_coalesce(row, "regime_decision", "regime"))


def _x_status(row: dict[str, Any]) -> str | None:
    status = _safe_str(_coalesce(row, "x_status", "x_state"))
    return status.lower() if status else None


def _normalized_status(row: dict[str, Any], *fields: str) -> str | None:
    value = _safe_str(_coalesce(row, *fields))
    return value.lower() if value else None


def _normalized_reason_codes(row: dict[str, Any], *fields: str) -> list[str]:
    value = _coalesce(row, *fields)
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(part).strip() for part in value]
    else:
        raw_items = [str(value).strip()]
    return [item.lower() for item in raw_items if item]


def _position_id(row: dict[str, Any]) -> str:
    return str(_coalesce(row, "position_id", "id", "token_address") or "unknown")


def _is_partial_evidence_row(row: dict[str, Any]) -> bool:
    if _safe_bool(row.get("partial_evidence_flag")) is True:
        return True
    for status in (
        _normalized_status(row, "bundle_evidence_status"),
        _normalized_status(row, "cluster_evidence_status"),
        _normalized_status(row, "continuation_status"),
        _normalized_status(row, "linkage_status"),
        _normalized_status(row, "runtime_signal_status"),
        _normalized_status(row, "tx_batch_status"),
    ):
        if status in _PARTIAL_EVIDENCE_STATUSES:
            return True
    return False


def _is_low_confidence_evidence_row(row: dict[str, Any]) -> bool:
    evidence_quality = _safe_float(row.get("evidence_quality_score"))
    sizing_confidence = _safe_float(row.get("sizing_confidence"))
    continuation_confidence = _safe_float(row.get("continuation_confidence"))
    linkage_confidence = _safe_float(row.get("linkage_confidence"))
    numeric_confidences = [
        value
        for value in (evidence_quality, sizing_confidence, continuation_confidence, linkage_confidence)
        if value is not None
    ]
    if numeric_confidences and min(numeric_confidences) < _LOW_EVIDENCE_CONFIDENCE_THRESHOLD:
        return True

    linkage_label = _normalized_status(row, "linkage_confidence")
    continuation_label = _normalized_status(row, "continuation_confidence")
    if linkage_label in _LOW_CONFIDENCE_LABELS or continuation_label in _LOW_CONFIDENCE_LABELS:
        return True

    for code in _normalized_reason_codes(row, "sizing_reason_codes", "linkage_reason_codes"):
        if "low_confidence" in code or code in {"weak_evidence_quality", "cluster_confidence_low"}:
            return True
    return False


def _is_evidence_conflict_row(row: dict[str, Any]) -> bool:
    return _safe_bool(row.get("evidence_conflict_flag")) is True


def _is_linkage_risk_underperformance_row(row: dict[str, Any]) -> bool:
    linkage_risk = max(
        [
            value
            for value in (
                _safe_float(row.get("linkage_risk_score")),
                _safe_float(row.get("creator_link_risk_score")),
                0.0,
            )
            if value is not None
        ]
    )
    if linkage_risk < _ELEVATED_LINKAGE_RISK_THRESHOLD:
        return False
    pnl = _net_pnl_pct(row)
    if pnl is None:
        return False
    return pnl <= 0.0


def _supporting_rows(rows: list[dict[str, Any]], limit: int = 8) -> list[str]:
    supporting = []
    for row in rows[:limit]:
        supporting.append(_position_id(row))
    return supporting


def _count_available(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if row.get(field) not in (None, ""))


def _pick_rows(rows: list[dict[str, Any]], predicate: Any) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        try:
            if predicate(row):
                selected.append(row)
        except Exception:
            continue
    return selected


def _compute_false_positive_rate(rows: list[dict[str, Any]]) -> float | None:
    pnls = [_net_pnl_pct(row) for row in rows]
    usable = [value for value in pnls if value is not None]
    if not usable:
        return None
    false_positives = [value for value in usable if value <= 0]
    return len(false_positives) / len(usable)


def _compute_confidence(sample_size: int, min_sample: int, warnings: list[str], expectancy: float | None) -> tuple[str, str]:
    if sample_size <= 0:
        return "none", "unavailable"
    if sample_size < min_sample:
        return "low", "insufficient_sample"
    if warnings:
        return "medium", "observed"
    if expectancy is None:
        return "medium", "observed"
    if abs(expectancy) >= 3.0:
        return "high", "observed"
    return "medium", "observed"


def _build_interpretation(slice_name: str, sample_size: int, expectancy: float | None, winrate: float | None, warnings: list[str]) -> str:
    if sample_size == 0:
        return f"{slice_name} unavailable because the required fields were not present in the analyzed artifacts."
    if "insufficient_sample" in warnings:
        return f"{slice_name} is only suggestive so far because the sample is below the minimum confidence threshold."
    direction = "mixed"
    if expectancy is not None:
        if expectancy > _MIN_MEANINGFUL_EDGE_PCT:
            direction = "positive"
        elif expectancy < -_MIN_MEANINGFUL_EDGE_PCT:
            direction = "negative"
    winrate_text = f" winrate={winrate:.2%}." if winrate is not None else ""
    return f"{slice_name} shows {direction} realized expectancy across {sample_size} rows.{winrate_text}"


def _recommendation_hint(slice_name: str, expectancy: float | None, sample_size: int, min_sample: int, positive: str | None, negative: str | None) -> str | None:
    if sample_size < min_sample:
        return None
    if expectancy is None:
        return None
    if expectancy <= -_MIN_MEANINGFUL_EDGE_PCT:
        return negative
    if expectancy >= _MIN_MEANINGFUL_EDGE_PCT:
        return positive
    return None


def _summarize_slice(
    slice_name: str,
    rows: list[dict[str, Any]],
    *,
    min_sample: int,
    required_fields: list[str] | None = None,
    positive_hint: str | None = None,
    negative_hint: str | None = None,
    extra_warnings: list[str] | None = None,
    interpretation_suffix: str | None = None,
) -> dict[str, Any]:
    required_fields = required_fields or []
    extra_warnings = list(extra_warnings or [])

    missing_fields = [field for field in required_fields if not any(row.get(field) not in (None, "") for row in rows)]
    usable_rows = [row for row in rows if _net_pnl_pct(row) is not None]
    pnl_values = [_net_pnl_pct(row) for row in usable_rows]
    pnls = [value for value in pnl_values if value is not None]
    wins = [value for value in pnls if value > 0]

    sample_size = len(usable_rows)
    winrate = (len(wins) / len(pnls)) if pnls else None
    expectancy = statistics.fmean(pnls) if pnls else None
    median_pnl = statistics.median(pnls) if pnls else None
    mean_pnl = expectancy
    false_positive_rate = _compute_false_positive_rate(usable_rows)

    warnings: list[str] = []
    if missing_fields:
        warnings.append(f"missing_fields:{','.join(sorted(missing_fields))}")
    if sample_size < min_sample:
        warnings.append("insufficient_sample")
    warnings.extend(extra_warnings)

    confidence, status = _compute_confidence(sample_size, min_sample, warnings if sample_size else [], expectancy)
    interpretation = _build_interpretation(slice_name, sample_size, expectancy, winrate, warnings)
    if interpretation_suffix and sample_size > 0:
        interpretation = f"{interpretation} {interpretation_suffix}"

    return {
        "slice_name": slice_name,
        "sample_size": sample_size,
        "supporting_rows": _supporting_rows(usable_rows),
        "winrate": winrate,
        "expectancy": expectancy,
        "median_pnl_pct": median_pnl,
        "mean_pnl_pct": mean_pnl,
        "false_positive_rate": false_positive_rate,
        "confidence": confidence,
        "status": status,
        "warnings": warnings,
        "interpretation": interpretation,
        "recommendation_hint": _recommendation_hint(slice_name, expectancy, sample_size, min_sample, positive_hint, negative_hint),
    }


def _rows_with_all_fields(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    return [row for row in rows if all(row.get(field) not in (None, "") for field in fields)]


def _regime_confidence_bucket_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "regime_confidence_lt_0.50": [],
        "regime_confidence_0.50_0.70": [],
        "regime_confidence_gte_0.70": [],
    }
    for row in rows:
        value = _safe_float(row.get("regime_confidence"))
        if value is None:
            continue
        if value < 0.50:
            buckets["regime_confidence_lt_0.50"].append(row)
        elif value < 0.70:
            buckets["regime_confidence_0.50_0.70"].append(row)
        else:
            buckets["regime_confidence_gte_0.70"].append(row)
    return buckets


def compute_regime_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    trend_rows = _pick_rows(rows, lambda row: _regime(row) == "TREND")
    scalp_rows = _pick_rows(rows, lambda row: _regime(row) == "SCALP")

    fast_failed_trend = _pick_rows(
        trend_rows,
        lambda row: (_net_pnl_pct(row) or 0.0) <= 0.0
        and (((_safe_float(row.get("hold_sec")) or 0.0) <= 300.0) or _exit_reason(row) in {"breakdown", "risk", "stop_loss", "scalp_stop_loss"}),
    )
    scalp_should_trend = _pick_rows(
        scalp_rows,
        lambda row: (_safe_float(row.get("mfe_pct")) is not None)
        and (_net_pnl_pct(row) is not None)
        and ((_safe_float(row.get("mfe_pct")) or 0.0) - (_net_pnl_pct(row) or 0.0) >= 8.0)
        and (((_safe_float(row.get("trend_survival_15m")) or 0.0) >= 0.50) or ((_safe_float(row.get("liquidity_refill_ratio_120s")) or 0.0) >= 1.0)),
    )

    trend_blocker_rows = _pick_rows(
        rows,
        lambda row: _safe_float(row.get("creator_cluster_penalty")) is not None
        or _safe_float(row.get("single_cluster_penalty")) is not None
        or _safe_float(row.get("bundle_sell_heavy_penalty")) is not None
        or _safe_float(row.get("retry_manipulation_penalty")) is not None,
    )

    blocker_counts: dict[str, int] = {
        "creator_cluster_penalty_high": sum(1 for row in rows if (_safe_float(row.get("creator_cluster_penalty")) or 0.0) >= 0.5),
        "single_cluster_penalty_high": sum(1 for row in rows if (_safe_float(row.get("single_cluster_penalty")) or 0.0) >= 0.5),
        "bundle_sell_heavy_penalty_high": sum(1 for row in rows if (_safe_float(row.get("bundle_sell_heavy_penalty")) or 0.0) >= 0.5),
        "retry_manipulation_penalty_high": sum(1 for row in rows if (_safe_float(row.get("retry_manipulation_penalty")) or 0.0) >= 0.5),
    }

    output = {
        "trend_promoted_but_failed_fast": _summarize_slice(
            "trend_promoted_but_failed_fast",
            fast_failed_trend,
            min_sample=min_sample,
            required_fields=["hold_sec", "net_pnl_pct"],
            negative_hint="consider not promoting low-refill / weak-reentry cases to trend",
            interpretation_suffix="Fast failures usually point to trend promotion quality rather than exit tuning alone.",
        ),
        "scalp_should_have_been_trend": _summarize_slice(
            "scalp_should_have_been_trend",
            scalp_should_trend,
            min_sample=min_sample,
            required_fields=["mfe_pct"],
            positive_hint="consider allowing more trend follow-through when continuation evidence is present",
            interpretation_suffix="These rows kept enough upside after the realized scalp exit to justify manual review.",
        ),
        "trend_vs_scalp_expectancy": {
            "slice_name": "trend_vs_scalp_expectancy",
            "sample_size": len([row for row in trend_rows + scalp_rows if _net_pnl_pct(row) is not None]),
            "supporting_rows": _supporting_rows(trend_rows + scalp_rows),
            "trend_expectancy": statistics.fmean([value for row in trend_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in trend_rows) else None,
            "scalp_expectancy": statistics.fmean([value for row in scalp_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in scalp_rows) else None,
            "expectancy_gap": (
                (statistics.fmean([value for row in trend_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in trend_rows) else 0.0)
                - (statistics.fmean([value for row in scalp_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in scalp_rows) else 0.0)
            ) if trend_rows and scalp_rows else None,
            "status": "observed" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "insufficient_sample",
            "confidence": "medium" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "low",
            "warnings": [] if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else ["insufficient_sample"],
            "interpretation": "Compares realized expectancy between TREND and SCALP classifications when both are present.",
            "recommendation_hint": None,
        },
        "trend_vs_scalp_winrate": {
            "slice_name": "trend_vs_scalp_winrate",
            "sample_size": len([row for row in trend_rows + scalp_rows if _net_pnl_pct(row) is not None]),
            "supporting_rows": _supporting_rows(trend_rows + scalp_rows),
            "trend_winrate": sum(1 for row in trend_rows if (_net_pnl_pct(row) or 0.0) > 0) / len([row for row in trend_rows if _net_pnl_pct(row) is not None]) if any(_net_pnl_pct(r) is not None for r in trend_rows) else None,
            "scalp_winrate": sum(1 for row in scalp_rows if (_net_pnl_pct(row) or 0.0) > 0) / len([row for row in scalp_rows if _net_pnl_pct(row) is not None]) if any(_net_pnl_pct(r) is not None for r in scalp_rows) else None,
            "status": "observed" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "insufficient_sample",
            "confidence": "medium" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "low",
            "warnings": [] if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else ["insufficient_sample"],
            "interpretation": "Compares realized winrate between TREND and SCALP classifications.",
            "recommendation_hint": None,
        },
        "trend_vs_scalp_median_pnl": {
            "slice_name": "trend_vs_scalp_median_pnl",
            "sample_size": len([row for row in trend_rows + scalp_rows if _net_pnl_pct(row) is not None]),
            "supporting_rows": _supporting_rows(trend_rows + scalp_rows),
            "trend_median_pnl_pct": statistics.median([value for row in trend_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in trend_rows) else None,
            "scalp_median_pnl_pct": statistics.median([value for row in scalp_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in scalp_rows) else None,
            "status": "observed" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "insufficient_sample",
            "confidence": "medium" if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else "low",
            "warnings": [] if len(trend_rows) >= min_sample and len(scalp_rows) >= min_sample else ["insufficient_sample"],
            "interpretation": "Compares median realized PnL between TREND and SCALP classifications.",
            "recommendation_hint": None,
        },
        "regime_blocker_frequency": {
            "slice_name": "regime_blocker_frequency",
            "sample_size": len(trend_blocker_rows),
            "supporting_rows": _supporting_rows(trend_blocker_rows),
            "blocker_counts": blocker_counts,
            "status": "observed" if trend_blocker_rows else "unavailable",
            "confidence": "medium" if len(trend_blocker_rows) >= min_sample else ("low" if trend_blocker_rows else "none"),
            "warnings": [] if len(trend_blocker_rows) >= min_sample else (["insufficient_sample"] if trend_blocker_rows else ["missing_fields:blocker_penalties"]),
            "interpretation": "Counts how often common regime blockers were present in the analyzed rows.",
            "recommendation_hint": None,
        },
    }

    confidence_buckets = _regime_confidence_bucket_rows(rows)
    output["regime_confidence_buckets"] = {
        "slice_name": "regime_confidence_buckets",
        "sample_size": sum(len(bucket_rows) for bucket_rows in confidence_buckets.values()),
        "supporting_rows": _supporting_rows([row for bucket_rows in confidence_buckets.values() for row in bucket_rows]),
        "buckets": {
            name: _summarize_slice(name, bucket_rows, min_sample=min_sample, required_fields=["regime_confidence"])
            for name, bucket_rows in confidence_buckets.items()
            if bucket_rows
        },
        "status": "observed" if confidence_buckets else "unavailable",
        "confidence": "medium" if sum(len(bucket_rows) for bucket_rows in confidence_buckets.values()) >= min_sample else "low",
        "warnings": [] if sum(len(bucket_rows) for bucket_rows in confidence_buckets.values()) >= min_sample else ["insufficient_sample"],
        "interpretation": "Buckets realized outcomes by regime confidence to show whether confidence aligns with realized quality.",
        "recommendation_hint": None,
    }
    return output


def compute_cluster_bundle_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    single_cluster = _pick_rows(rows, lambda row: (_safe_float(row.get("single_cluster_penalty")) or 0.0) >= 0.5 or (_safe_float(row.get("num_unique_clusters_first_60s")) or 99.0) <= 1.0)
    multi_cluster = _pick_rows(rows, lambda row: (_safe_float(row.get("num_unique_clusters_first_60s")) or 0.0) >= 2.0 or (_safe_float(row.get("organic_multi_cluster_bonus")) or 0.0) > 0)
    creator_linked = _pick_rows(rows, lambda row: (_safe_bool(row.get("creator_in_cluster_flag")) is True) or ((_safe_float(row.get("creator_cluster_penalty")) or 0.0) >= 0.5))
    high_concentration = _pick_rows(rows, lambda row: (_safe_float(row.get("cluster_concentration_ratio")) or 0.0) >= 0.6)
    sell_heavy = _pick_rows(rows, lambda row: (_safe_float(row.get("bundle_sell_heavy_penalty")) or 0.0) >= 0.5 or _safe_str(row.get("bundle_composition_dominant")) == "sell_only")
    retry_heavy = _pick_rows(rows, lambda row: (_safe_float(row.get("retry_manipulation_penalty")) or 0.0) >= 0.5 or _safe_str(row.get("bundle_failure_retry_pattern")) in {"retry_heavy", "manipulative", "multi_retry"})
    cross_block = _pick_rows(rows, lambda row: row.get("cross_block_bundle_correlation") not in (None, ""))
    tip_efficiency = _pick_rows(rows, lambda row: row.get("bundle_tip_efficiency") not in (None, ""))

    return {
        "single_cluster_underperformance": _summarize_slice(
            "single_cluster_underperformance",
            single_cluster,
            min_sample=min_sample,
            required_fields=["single_cluster_penalty"],
            negative_hint="consider increasing caution for high cluster concentration",
        ),
        "multi_cluster_outperformance": _summarize_slice(
            "multi_cluster_outperformance",
            multi_cluster,
            min_sample=min_sample,
            required_fields=["num_unique_clusters_first_60s"],
            positive_hint="multi-cluster organic support looks healthier than single-cluster concentration",
        ),
        "creator_linked_underperformance": _summarize_slice(
            "creator_linked_underperformance",
            creator_linked,
            min_sample=min_sample,
            required_fields=["creator_in_cluster_flag"],
            negative_hint="consider tightening trend promotion when creator-linked evidence is present",
        ),
        "high_cluster_concentration_underperformance": _summarize_slice(
            "high_cluster_concentration_underperformance",
            high_concentration,
            min_sample=min_sample,
            required_fields=["cluster_concentration_ratio"],
            negative_hint="consider increasing caution for high cluster concentration",
        ),
        "bundle_sell_heavy_underperformance": _summarize_slice(
            "bundle_sell_heavy_underperformance",
            sell_heavy,
            min_sample=min_sample,
            required_fields=["bundle_sell_heavy_penalty"],
            negative_hint="consider penalizing sell-heavy bundle composition more heavily in manual reviews",
        ),
        "retry_pattern_underperformance": _summarize_slice(
            "retry_pattern_underperformance",
            retry_heavy,
            min_sample=min_sample,
            required_fields=["retry_manipulation_penalty"],
            negative_hint="consider increasing caution around retry-heavy bundle behavior",
        ),
        "cross_block_correlation_slices": _summarize_slice(
            "cross_block_correlation_slices",
            cross_block,
            min_sample=min_sample,
            required_fields=["cross_block_bundle_correlation"],
        ),
        "bundle_tip_efficiency_slices": _summarize_slice(
            "bundle_tip_efficiency_slices",
            tip_efficiency,
            min_sample=min_sample,
            required_fields=["bundle_tip_efficiency"],
        ),
    }


def compute_continuation_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    low_refill = _pick_rows(rows, lambda row: (_safe_float(row.get("liquidity_refill_ratio_120s")) or 99.0) < 0.8)
    weak_reentry = _pick_rows(rows, lambda row: (_safe_float(row.get("seller_reentry_ratio")) or 99.0) < 0.3)
    slow_recovery = _pick_rows(rows, lambda row: (_safe_float(row.get("liquidity_shock_recovery_sec")) or 0.0) > 180.0)
    cluster_failure = _pick_rows(rows, lambda row: (_safe_float(row.get("cluster_sell_concentration_120s")) or 0.0) >= 0.6)
    organic_buyers = _pick_rows(rows, lambda row: (_safe_float(row.get("net_unique_buyers_60s")) or 0.0) >= 15.0)
    smart_wallet_support = _pick_rows(rows, lambda row: (_safe_float(row.get("smart_wallet_dispersion_score")) or 0.0) >= 0.6)
    x_velocity_support = _pick_rows(rows, lambda row: (_safe_float(row.get("x_author_velocity_5m")) or 0.0) >= 0.6)

    return {
        "failed_liquidity_refill_underperformance": _summarize_slice(
            "failed_liquidity_refill_underperformance",
            low_refill,
            min_sample=min_sample,
            required_fields=["liquidity_refill_ratio_120s"],
            negative_hint="consider not promoting low-refill / weak-reentry cases to trend",
        ),
        "weak_reentry_underperformance": _summarize_slice(
            "weak_reentry_underperformance",
            weak_reentry,
            min_sample=min_sample,
            required_fields=["seller_reentry_ratio"],
            negative_hint="consider not promoting low-refill / weak-reentry cases to trend",
        ),
        "shock_not_recovered_underperformance": _summarize_slice(
            "shock_not_recovered_underperformance",
            slow_recovery,
            min_sample=min_sample,
            required_fields=["liquidity_shock_recovery_sec"],
            negative_hint="consider adding extra patience or avoiding trend promotion when shock recovery stays slow",
        ),
        "cluster_distribution_failure_slices": _summarize_slice(
            "cluster_distribution_failure_slices",
            cluster_failure,
            min_sample=min_sample,
            required_fields=["cluster_sell_concentration_120s"],
            negative_hint="cluster-distribution failures deserve extra caution in bundle-heavy names",
        ),
        "organic_buyer_flow_positive_slices": _summarize_slice(
            "organic_buyer_flow_positive_slices",
            organic_buyers,
            min_sample=min_sample,
            required_fields=["net_unique_buyers_60s"],
            positive_hint="organic buyer flow looks supportive enough to preserve follow-through candidates",
        ),
        "smart_wallet_dispersion_supportive_slices": _summarize_slice(
            "smart_wallet_dispersion_supportive_slices",
            smart_wallet_support,
            min_sample=min_sample,
            required_fields=["smart_wallet_dispersion_score"],
            positive_hint="smart-wallet dispersion looks supportive rather than concentrated/manipulative",
        ),
        "x_author_velocity_supportive_slices": _summarize_slice(
            "x_author_velocity_supportive_slices",
            x_velocity_support,
            min_sample=min_sample,
            required_fields=["x_author_velocity_5m"],
            positive_hint="healthy X author velocity appears supportive, but still manual-only",
        ),
    }


def compute_degraded_x_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    degraded_rows = _pick_rows(rows, lambda row: _x_status(row) in _DEGRADED_X_STATUSES)
    healthy_rows = _pick_rows(rows, lambda row: _x_status(row) in _HEALTHY_X_STATUSES)
    salvage_rows = _pick_rows(degraded_rows, lambda row: (_net_pnl_pct(row) or 0.0) > 0 and (((_safe_float(row.get("organic_multi_cluster_bonus")) or 0.0) > 0) or ((_safe_float(row.get("net_unique_buyers_60s")) or 0.0) >= 15.0)))
    small_size_rows = _pick_rows(degraded_rows, lambda row: (_safe_float(row.get("size_sol")) or _safe_float(row.get("notional_sol")) or 99.0) <= 0.5)

    degraded_expectancy = statistics.fmean([value for row in degraded_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in degraded_rows) else None
    healthy_expectancy = statistics.fmean([value for row in healthy_rows if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in healthy_rows) else None

    output = {
        "degraded_x_vs_healthy_x": {
            "slice_name": "degraded_x_vs_healthy_x",
            "sample_size": len([row for row in degraded_rows + healthy_rows if _net_pnl_pct(row) is not None]),
            "supporting_rows": _supporting_rows(degraded_rows + healthy_rows),
            "degraded_sample_size": len([row for row in degraded_rows if _net_pnl_pct(row) is not None]),
            "healthy_sample_size": len([row for row in healthy_rows if _net_pnl_pct(row) is not None]),
            "degraded_expectancy": degraded_expectancy,
            "healthy_expectancy": healthy_expectancy,
            "expectancy_gap": (degraded_expectancy - healthy_expectancy) if degraded_expectancy is not None and healthy_expectancy is not None else None,
            "degraded_false_positive_rate": _compute_false_positive_rate(degraded_rows),
            "healthy_false_positive_rate": _compute_false_positive_rate(healthy_rows),
            "confidence": "medium" if len(degraded_rows) >= min_sample and len(healthy_rows) >= min_sample else "low",
            "status": "observed" if degraded_rows or healthy_rows else "unavailable",
            "warnings": [] if len(degraded_rows) >= min_sample and len(healthy_rows) >= min_sample else ["insufficient_sample"],
            "interpretation": "Compares degraded-X rows against healthy-X rows without assuming degraded X is always bad.",
            "recommendation_hint": "consider keeping degraded X in reduced-size mode" if len(degraded_rows) >= min_sample and degraded_expectancy is not None and degraded_expectancy <= (healthy_expectancy or 0.0) else None,
        },
        "degraded_x_salvage_cases": _summarize_slice(
            "degraded_x_salvage_cases",
            salvage_rows,
            min_sample=min_sample,
            required_fields=["x_status"],
            positive_hint="some degraded-X names can still work when organic/buyer support is visible",
        ),
        "degraded_x_false_positive_rate": _summarize_slice(
            "degraded_x_false_positive_rate",
            degraded_rows,
            min_sample=min_sample,
            required_fields=["x_status"],
            negative_hint="consider keeping degraded X in reduced-size mode",
        ),
        "degraded_x_small_size_performance": _summarize_slice(
            "degraded_x_small_size_performance",
            small_size_rows,
            min_sample=min_sample,
            required_fields=["size_sol"],
            positive_hint="reduced-size degraded-X rows behaved more safely than full-size exposure",
        ),
    }
    return output


def compute_evidence_quality_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    partial_rows = _pick_rows(rows, _is_partial_evidence_row)
    low_confidence_rows = _pick_rows(rows, _is_low_confidence_evidence_row)
    evidence_conflict_rows = _pick_rows(rows, _is_evidence_conflict_row)
    degraded_x_rows = _pick_rows(rows, lambda row: _x_status(row) in _DEGRADED_X_STATUSES)
    degraded_x_salvage_rows = _pick_rows(degraded_x_rows, lambda row: (_net_pnl_pct(row) or 0.0) > 0.0)
    linkage_risk_rows = _pick_rows(rows, _is_linkage_risk_underperformance_row)
    healthy_rows = _pick_rows(
        rows,
        lambda row: not _is_partial_evidence_row(row)
        and not _is_low_confidence_evidence_row(row)
        and not _is_evidence_conflict_row(row)
        and (_x_status(row) not in _DEGRADED_X_STATUSES)
        and not _is_linkage_risk_underperformance_row(row),
    )

    return {
        "partial_evidence_trades": _summarize_slice(
            "partial_evidence_trades",
            partial_rows,
            min_sample=min_sample,
            negative_hint="review whether partial-evidence rows need stricter SCALP-only routing or smaller size",
            interpretation_suffix="This bucket is direct-field-driven: explicit partial flags or partial core evidence statuses qualify a row.",
        ),
        "low_confidence_evidence_trades": _summarize_slice(
            "low_confidence_evidence_trades",
            low_confidence_rows,
            min_sample=min_sample,
            negative_hint="review whether low-confidence evidence should stay reduced-size even when other metrics look supportive",
            interpretation_suffix="This bucket prefers existing scalar confidence fields and low-confidence reason codes over opaque heuristics.",
        ),
        "evidence_conflict_trades": _summarize_slice(
            "evidence_conflict_trades",
            evidence_conflict_rows,
            min_sample=min_sample,
            required_fields=["evidence_conflict_flag"],
            negative_hint="review whether conflicting evidence should trigger stronger caution or smaller size",
            interpretation_suffix="Rows are included only when the artifact explicitly marks evidence_conflict_flag=true.",
        ),
        "degraded_x_trades": _summarize_slice(
            "degraded_x_trades",
            degraded_x_rows,
            min_sample=min_sample,
            required_fields=["x_status"],
            negative_hint="review whether degraded-X rows still deserve reduced-size-only handling",
            interpretation_suffix="Rows are included directly from x_status=degraded-style states.",
        ),
        "degraded_x_salvage_cases": _summarize_slice(
            "degraded_x_salvage_cases",
            degraded_x_salvage_rows,
            min_sample=min_sample,
            required_fields=["x_status"],
            positive_hint="some degraded-X rows still realize positive pnl and can be reviewed as salvage rather than automatic rejects",
            interpretation_suffix="Salvage uses a simple calibration rule: degraded-X plus positive realized net_pnl_pct.",
        ),
        "linkage_risk_underperformance": _summarize_slice(
            "linkage_risk_underperformance",
            linkage_risk_rows,
            min_sample=min_sample,
            negative_hint="review whether elevated linkage/manipulation risk needs stronger penalty or smaller size",
            interpretation_suffix="Rows require elevated linkage risk and non-positive realized pnl so the slice stays easy to reproduce.",
        ),
        "healthy_evidence_trades": _summarize_slice(
            "healthy_evidence_trades",
            healthy_rows,
            min_sample=min_sample,
            required_fields=["net_pnl_pct"],
            positive_hint="healthy-evidence rows can serve as the manual comparison baseline for degraded or conflicting buckets",
            interpretation_suffix="This optional comparison bucket excludes degraded, partial, conflicting, low-confidence, and elevated-linkage-risk underperformance rows.",
        ),
    }


def compute_exit_failure_slices(rows: list[dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, dict[str, Any]]:
    cluster_dump = _pick_rows(rows, lambda row: _exit_reason(row) in {"cluster_dump", "cluster_dump_exit"})
    creator_cluster_exit = _pick_rows(rows, lambda row: _exit_reason(row) in {"creator_cluster_risk", "creator_cluster_exit"} or ((_safe_bool(row.get("creator_in_cluster_flag")) is True) and (_net_pnl_pct(row) or 0.0) <= 0))
    bundle_failure_spike = _pick_rows(rows, lambda row: _exit_reason(row) in {"bundle_failure_spike", "bundle_failure_exit"} or ((_safe_float(row.get("bundle_sell_heavy_penalty")) or 0.0) >= 0.5 and (_net_pnl_pct(row) or 0.0) <= 0))
    retry_manipulation_exit = _pick_rows(rows, lambda row: _exit_reason(row) in {"retry_manipulation", "retry_manipulation_exit"} or ((_safe_float(row.get("retry_manipulation_penalty")) or 0.0) >= 0.5 and (_net_pnl_pct(row) or 0.0) <= 0))
    partial_exit = _pick_rows(rows, lambda row: (_safe_float(row.get("partial_exit_count")) or 0.0) > 0)
    full_exit = _pick_rows(rows, lambda row: (_safe_float(row.get("partial_exit_count")) or 0.0) <= 0)

    partial_expectancy = statistics.fmean([value for row in partial_exit if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in partial_exit) else None
    full_expectancy = statistics.fmean([value for row in full_exit if (value := _net_pnl_pct(row)) is not None]) if any(_net_pnl_pct(r) is not None for r in full_exit) else None

    return {
        "cluster_dump_exit_performance": _summarize_slice(
            "cluster_dump_exit_performance",
            cluster_dump,
            min_sample=min_sample,
            required_fields=["exit_reason_final"],
        ),
        "creator_cluster_exit_risk_performance": _summarize_slice(
            "creator_cluster_exit_risk_performance",
            creator_cluster_exit,
            min_sample=min_sample,
            required_fields=["creator_in_cluster_flag"],
            negative_hint="consider tightening trend promotion when creator-linked evidence is present",
        ),
        "bundle_failure_spike_exit_performance": _summarize_slice(
            "bundle_failure_spike_exit_performance",
            bundle_failure_spike,
            min_sample=min_sample,
            required_fields=["bundle_sell_heavy_penalty"],
        ),
        "retry_manipulation_exit_performance": _summarize_slice(
            "retry_manipulation_exit_performance",
            retry_manipulation_exit,
            min_sample=min_sample,
            required_fields=["retry_manipulation_penalty"],
        ),
        "partial_exit_vs_full_exit_outcomes": {
            "slice_name": "partial_exit_vs_full_exit_outcomes",
            "sample_size": len([row for row in partial_exit + full_exit if _net_pnl_pct(row) is not None]),
            "supporting_rows": _supporting_rows(partial_exit + full_exit),
            "partial_exit_expectancy": partial_expectancy,
            "full_exit_expectancy": full_expectancy,
            "expectancy_gap": (partial_expectancy - full_expectancy) if partial_expectancy is not None and full_expectancy is not None else None,
            "confidence": "medium" if len(partial_exit) >= min_sample and len(full_exit) >= min_sample else "low",
            "status": "observed" if partial_exit or full_exit else "unavailable",
            "warnings": [] if len(partial_exit) >= min_sample and len(full_exit) >= min_sample else ["insufficient_sample"],
            "interpretation": "Compares realized outcomes for positions that used partial exits versus full exits only.",
            "recommendation_hint": None,
        },
    }


def compute_recommendation_inputs_from_slices(slice_groups: dict[str, dict[str, Any]], *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> dict[str, Any]:
    actionable: list[dict[str, Any]] = []
    low_sample: list[str] = []
    warnings: list[str] = []
    for group_name, group in slice_groups.items():
        for slice_name, payload in group.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("status") == "insufficient_sample":
                low_sample.append(slice_name)
            if payload.get("warnings"):
                warnings.extend([f"{slice_name}:{warning}" for warning in payload.get("warnings", [])])
            hint = payload.get("recommendation_hint")
            sample_size = int(payload.get("sample_size", 0) or 0)
            expectancy = payload.get("expectancy")
            if hint and sample_size >= min_sample:
                actionable.append(
                    {
                        "group": group_name,
                        "slice_name": slice_name,
                        "sample_size": sample_size,
                        "expectancy": expectancy,
                        "confidence": payload.get("confidence"),
                        "recommendation_hint": hint,
                    }
                )
    actionable.sort(key=lambda item: (abs(item.get("expectancy") or 0.0), item["sample_size"]), reverse=True)
    return {
        "actionable_slices": actionable[:8],
        "low_sample_slices": sorted(set(low_sample)),
        "warnings": sorted(set(warnings)),
        "manual_only": True,
    }


def compute_analyzer_slices(
    rows: list[dict[str, Any]],
    *,
    min_sample: int = _DEFAULT_MIN_SAMPLE,
    run_id: str = "",
    source: str = "trade_feature_matrix",
    as_of: str | None = None,
) -> dict[str, Any]:
    regime = compute_regime_slices(rows, min_sample=min_sample)
    cluster_bundle = compute_cluster_bundle_slices(rows, min_sample=min_sample)
    continuation = compute_continuation_slices(rows, min_sample=min_sample)
    degraded_x = compute_degraded_x_slices(rows, min_sample=min_sample)
    evidence_quality = compute_evidence_quality_slices(rows, min_sample=min_sample)
    exit_failure = compute_exit_failure_slices(rows, min_sample=min_sample)
    slice_groups = {
        "regime": regime,
        "cluster_bundle": cluster_bundle,
        "continuation": continuation,
        "degraded_x": degraded_x,
        "evidence_quality": evidence_quality,
        "exit_failure": exit_failure,
    }
    recommendation_inputs = compute_recommendation_inputs_from_slices(slice_groups, min_sample=min_sample)
    low_confidence_count = sum(
        1
        for group in slice_groups.values()
        for payload in group.values()
        if isinstance(payload, dict) and payload.get("status") in {"insufficient_sample", "unavailable"}
    )
    return {
        "metadata": {
            "contract_version": _ANALYZER_SLICES_CONTRACT_VERSION,
            "run_id": run_id,
            "source": source,
            "as_of": as_of,
            "minimum_sample": min_sample,
            "row_count": len(rows),
        },
        "slice_groups": slice_groups,
        "evidence_quality_slices": evidence_quality,
        "recommendation_inputs": recommendation_inputs,
        "status": "ok",
        "warnings": recommendation_inputs.get("warnings", []),
        "coverage": {
            "available_groups": [group for group, payload in slice_groups.items() if payload],
            "low_confidence_slice_count": low_confidence_count,
        },
    }


__all__ = [
    "bucketize_metric",
    "slice_positions",
    "compute_analyzer_slices",
    "compute_regime_slices",
    "compute_cluster_bundle_slices",
    "compute_continuation_slices",
    "compute_degraded_x_slices",
    "compute_evidence_quality_slices",
    "compute_exit_failure_slices",
    "compute_recommendation_inputs_from_slices",
]
