"""Offline-only feature importance analysis over replay-derived trade matrices."""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.feature_groups import feature_group_for_name
from utils.io import ensure_dir, write_json
from utils.logger import log_info, log_warning

_ANALYSIS_CONTRACT_VERSION = "offline_feature_importance.v1"
_MIN_FEATURE_COVERAGE = 0.35
_LOW_SAMPLE_ROWS = 12
_LOW_POSITIVE_CLASS_COUNT = 4
_MAX_FEATURE_CARDINALITY = 16
_EXCLUDED_FEATURES = {
    "profitable_trade_flag",
    "trend_success_flag",
    "fast_failure_flag",
    "net_pnl_pct",
    "gross_pnl_pct",
    "hold_sec",
    "exit_reason_final",
    "mfe_pct",
    "mae_pct",
    "mfe_pct_240s",
    "mae_pct_240s",
    "trend_survival_15m",
    "trend_survival_60m",
    "time_to_first_profit_sec",
    "exit_decision",
    "exit_flags",
    "exit_warnings",
    "price_path",
    "price_trajectory",
    "trajectory",
    "observed_prices",
    "lifecycle_path",
    "outcome_price_path",
}


class FeatureMatrixLoadError(ValueError):
    """Raised when a feature matrix cannot be analyzed safely."""



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
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None



def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None



def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return None
    if isinstance(value, list):
        return None
    bool_value = _safe_bool(value)
    if bool_value is not None:
        return bool_value
    numeric_value = _safe_float(value)
    if numeric_value is not None:
        return numeric_value
    return _safe_str(value)



def _build_target_value(row: dict[str, Any], target_name: str) -> bool | None:
    net_pnl_pct = _safe_float(row.get("net_pnl_pct"))
    hold_sec = _safe_float(row.get("hold_sec"))
    trend_survival_15m = _safe_float(row.get("trend_survival_15m"))
    mfe_pct_240s = _safe_float(row.get("mfe_pct_240s"))
    time_to_first_profit_sec = _safe_float(row.get("time_to_first_profit_sec"))
    mae_pct_240s = _safe_float(row.get("mae_pct_240s"))
    exit_reason_final = (_safe_str(row.get("exit_reason_final")) or "").lower()

    if target_name == "profitable_trade_flag":
        if net_pnl_pct is None:
            return None
        return net_pnl_pct > 0.0

    if target_name == "trend_success_flag":
        evidence: list[bool] = []
        if trend_survival_15m is not None:
            evidence.append(trend_survival_15m >= 0.45)
        if mfe_pct_240s is not None:
            evidence.append(mfe_pct_240s >= 6.0)
        if net_pnl_pct is not None:
            evidence.append(net_pnl_pct >= 4.0)
        if time_to_first_profit_sec is not None:
            evidence.append(time_to_first_profit_sec <= 180.0)
        if not evidence:
            return None
        return sum(1 for item in evidence if item) >= 3 if len(evidence) >= 3 else all(evidence)

    if target_name == "fast_failure_flag":
        evidence: list[bool] = []
        if net_pnl_pct is not None and hold_sec is not None:
            evidence.append(net_pnl_pct < 0.0 and hold_sec <= 300.0)
        if mae_pct_240s is not None:
            evidence.append(mae_pct_240s <= -6.0)
        if exit_reason_final:
            evidence.append(any(flag in exit_reason_final for flag in ("stop", "breakdown", "rug", "fail")))
        if not evidence:
            return None
        return any(evidence)

    raise KeyError(f"Unsupported target: {target_name}")


TARGET_DEFINITIONS: dict[str, dict[str, str]] = {
    "profitable_trade_flag": {
        "target_name": "profitable_trade_flag",
        "target_type": "binary",
        "description": "Offline binary target for positive net PnL trades.",
    },
    "trend_success_flag": {
        "target_name": "trend_success_flag",
        "target_type": "binary",
        "description": "Offline binary target for stronger trend-like success behavior using survival, MFE, PnL, and early-profit evidence.",
    },
    "fast_failure_flag": {
        "target_name": "fast_failure_flag",
        "target_type": "binary",
        "description": "Offline binary target for rapid bad outcomes or early failure behavior.",
    },
}



def load_feature_matrix(path: str | Path) -> dict[str, Any]:
    matrix_path = Path(path).expanduser().resolve()
    if not matrix_path.exists():
        raise FeatureMatrixLoadError(f"Feature matrix not found: {matrix_path}")

    usable_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    total_rows = 0
    malformed_rows = 0

    for line_number, raw_line in enumerate(matrix_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        total_rows += 1
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            malformed_rows += 1
            excluded_rows.append({"line_number": line_number, "reason": "malformed_json"})
            continue

        if not isinstance(payload, dict):
            excluded_rows.append({"line_number": line_number, "reason": "row_not_object"})
            continue

        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            scalar = _normalize_scalar(value)
            if scalar is not None:
                normalized[key] = scalar

        target_capable = any(_build_target_value(payload, target_name) is not None for target_name in TARGET_DEFINITIONS)
        if not normalized or not target_capable:
            excluded_rows.append({"line_number": line_number, "reason": "no_usable_scalar_fields_or_targets"})
            continue
        usable_rows.append(normalized)

    if not usable_rows:
        raise FeatureMatrixLoadError("Feature matrix contains no usable rows for offline analysis")

    payload = {
        "path": str(matrix_path),
        "rows": usable_rows,
        "row_count": len(usable_rows),
        "total_rows_seen": total_rows,
        "excluded_row_count": len(excluded_rows),
        "malformed_row_count": malformed_rows,
        "excluded_rows": excluded_rows,
    }
    log_info(
        "feature_matrix_loaded",
        path=str(matrix_path),
        row_count=len(usable_rows),
        excluded_row_count=len(excluded_rows),
        malformed_row_count=malformed_rows,
    )
    return payload



def _infer_feature_names(rows: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        names.update(row.keys())
    candidates = [name for name in names if name not in _EXCLUDED_FEATURES and feature_group_for_name(name) != "meta_features"]
    return sorted(candidates)



def _target_rows(rows: list[dict[str, Any]], target_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    filtered_rows: list[dict[str, Any]] = []
    positives = 0
    negatives = 0
    for row in rows:
        target_value = _build_target_value(row, target_name)
        if target_value is None:
            continue
        enriched = dict(row)
        enriched[target_name] = target_value
        filtered_rows.append(enriched)
        if target_value:
            positives += 1
        else:
            negatives += 1

    warnings: list[str] = []
    if len(filtered_rows) < _LOW_SAMPLE_ROWS:
        warnings.append(f"low sample size for {target_name}: {len(filtered_rows)} rows")
    if min(positives, negatives) < _LOW_POSITIVE_CLASS_COUNT:
        warnings.append(
            f"class imbalance for {target_name}: positives={positives} negatives={negatives}"
        )
    target_summary = {
        **TARGET_DEFINITIONS[target_name],
        "sample_size": len(filtered_rows),
        "positive_count": positives,
        "negative_count": negatives,
        "warnings": warnings,
    }
    log_info(
        "offline_target_built",
        target_name=target_name,
        sample_size=len(filtered_rows),
        positive_count=positives,
        negative_count=negatives,
        warning_count=len(warnings),
    )
    return filtered_rows, target_summary



def _numeric_importance(values: list[float], targets: list[bool]) -> tuple[float, str | None]:
    positives = [value for value, target in zip(values, targets) if target]
    negatives = [value for value, target in zip(values, targets) if not target]
    if len(positives) < 2 or len(negatives) < 2:
        return 0.0, None
    overall = values
    variance = statistics.pvariance(overall) if len(overall) > 1 else 0.0
    if variance <= 0:
        return 0.0, None
    score = abs(statistics.fmean(positives) - statistics.fmean(negatives)) / math.sqrt(variance)
    direction = "positive_association" if statistics.fmean(positives) >= statistics.fmean(negatives) else "negative_association"
    return score, direction



def _categorical_importance(values: list[str | bool], targets: list[bool]) -> tuple[float, str | None, int]:
    by_value: dict[str, list[bool]] = {}
    for value, target in zip(values, targets):
        key = str(value)
        by_value.setdefault(key, []).append(target)
    if len(by_value) <= 1:
        return 0.0, None, len(by_value)
    baseline = sum(1 for target in targets if target) / len(targets)
    weighted_gap = 0.0
    best_direction = 0.0
    for outcomes in by_value.values():
        local_rate = sum(1 for item in outcomes if item) / len(outcomes)
        delta = local_rate - baseline
        weighted_gap += abs(delta) * (len(outcomes) / len(targets))
        if abs(delta) > abs(best_direction):
            best_direction = delta
    direction = None
    if best_direction > 0:
        direction = "positive_association"
    elif best_direction < 0:
        direction = "negative_association"
    return weighted_gap, direction, len(by_value)



def _feature_importance_for_target(rows: list[dict[str, Any]], target_name: str, feature_names: list[str]) -> dict[str, Any]:
    per_feature_rows: list[dict[str, Any]] = []
    target_values = [bool(row[target_name]) for row in rows]
    warnings: list[str] = []

    for feature_name in feature_names:
        observed_values = [row.get(feature_name) for row in rows if row.get(feature_name) is not None]
        coverage_ratio = len(observed_values) / len(rows) if rows else 0.0
        missing_ratio = 1.0 - coverage_ratio
        feature_warnings: list[str] = []

        if coverage_ratio < _MIN_FEATURE_COVERAGE:
            feature_warnings.append(f"low coverage ({coverage_ratio:.2%})")
        aligned_values: list[Any] = []
        aligned_targets: list[bool] = []
        for row in rows:
            value = row.get(feature_name)
            if value is None:
                continue
            aligned_values.append(value)
            aligned_targets.append(bool(row[target_name]))

        if len(aligned_values) < _LOW_SAMPLE_ROWS:
            feature_warnings.append(f"limited observed rows ({len(aligned_values)})")

        importance_score = 0.0
        direction_hint: str | None = None
        method = "univariate_unknown"
        status = "ok"

        if aligned_values:
            numeric_values = [_safe_float(value) for value in aligned_values]
            if all(value is not None for value in numeric_values):
                importance_score, direction_hint = _numeric_importance([float(value) for value in numeric_values if value is not None], aligned_targets)
                method = "univariate_numeric_effect_size"
            else:
                categorical_values = [value for value in aligned_values if isinstance(value, (str, bool))]
                if len(categorical_values) == len(aligned_values):
                    importance_score, direction_hint, cardinality = _categorical_importance(categorical_values, aligned_targets)
                    method = "univariate_categorical_rate_gap"
                    if cardinality > _MAX_FEATURE_CARDINALITY:
                        feature_warnings.append(f"high cardinality ({cardinality})")
                else:
                    status = "excluded"
                    feature_warnings.append("mixed/non-scalar values unsupported")
        else:
            status = "excluded"
            feature_warnings.append("feature absent for analyzed target rows")

        if importance_score == 0.0 and status == "ok" and len(feature_warnings) > 0:
            status = "weak_signal"
        if feature_warnings:
            warnings.extend(f"{target_name}:{feature_name}:{warning}" for warning in feature_warnings)

        per_feature_rows.append(
            {
                "feature_name": feature_name,
                "feature_group": feature_group_for_name(feature_name),
                "importance_score": round(float(importance_score), 6),
                "coverage_ratio": round(float(coverage_ratio), 6),
                "missing_ratio": round(float(missing_ratio), 6),
                "direction_hint": direction_hint,
                "target_name": target_name,
                "method": method,
                "status": status,
                "observed_rows": len(aligned_values),
                "warnings": feature_warnings,
            }
        )

    ranked_rows = sorted(
        per_feature_rows,
        key=lambda item: (item["importance_score"], item["coverage_ratio"], item["feature_name"]),
        reverse=True,
    )
    for index, item in enumerate(ranked_rows, start=1):
        item["importance_rank"] = index

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in ranked_rows:
        grouped.setdefault(row["feature_group"], []).append(row)

    grouped_rows: list[dict[str, Any]] = []
    for group_name, items in sorted(grouped.items()):
        scores = [float(item["importance_score"]) for item in items]
        coverage = [float(item["coverage_ratio"]) for item in items]
        grouped_rows.append(
            {
                "feature_group": group_name,
                "target_name": target_name,
                "feature_count": len(items),
                "importance_score_total": round(sum(scores), 6),
                "importance_score_avg": round(statistics.fmean(scores), 6) if scores else 0.0,
                "coverage_ratio_avg": round(statistics.fmean(coverage), 6) if coverage else 0.0,
                "top_features": [item["feature_name"] for item in items[:3]],
            }
        )
    grouped_rows.sort(key=lambda item: (item["importance_score_total"], item["coverage_ratio_avg"]), reverse=True)

    return {
        "target_name": target_name,
        "grouped_importance": grouped_rows,
        "per_feature_importance": ranked_rows,
        "warnings": sorted(set(warnings)),
    }



def compute_offline_feature_importance(
    matrix_payload: dict[str, Any],
    *,
    target_names: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    rows = list(matrix_payload.get("rows", []))
    if not rows:
        raise FeatureMatrixLoadError("Cannot compute importance from an empty matrix payload")

    feature_names = _infer_feature_names(rows)
    selected_targets = target_names or list(TARGET_DEFINITIONS)
    results: list[dict[str, Any]] = []
    target_definitions: list[dict[str, Any]] = []
    overall_warnings: list[str] = []

    log_info(
        "offline_feature_importance_started",
        source_path=matrix_payload.get("path"),
        row_count=len(rows),
        feature_count=len(feature_names),
        target_count=len(selected_targets),
    )

    for target_name in selected_targets:
        target_rows, target_summary = _target_rows(rows, target_name)
        target_definitions.append(target_summary)
        target_result = _feature_importance_for_target(target_rows, target_name, feature_names)
        if target_summary["warnings"]:
            log_warning(
                "feature_importance_low_sample_warning",
                target_name=target_name,
                warnings=target_summary["warnings"],
            )
        if any("low coverage" in warning for warning in target_result["warnings"]):
            log_warning(
                "feature_importance_missingness_warning",
                target_name=target_name,
                warning_count=len(target_result["warnings"]),
            )
        log_info(
            "feature_importance_computed",
            target_name=target_name,
            sample_size=target_summary["sample_size"],
            feature_count=len(feature_names),
            grouped_count=len(target_result["grouped_importance"]),
        )
        results.append(target_result)
        overall_warnings.extend(target_summary["warnings"])
        overall_warnings.extend(target_result["warnings"])

    output = {
        "analysis_contract_version": _ANALYSIS_CONTRACT_VERSION,
        "generated_at_utc": generated_at
        or datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "analysis_only": True,
        "not_for_online_decisioning": True,
        "association_only": True,
        "input_artifact": {
            "path": matrix_payload.get("path"),
            "row_count": matrix_payload.get("row_count", 0),
            "total_rows_seen": matrix_payload.get("total_rows_seen", 0),
            "excluded_row_count": matrix_payload.get("excluded_row_count", 0),
            "malformed_row_count": matrix_payload.get("malformed_row_count", 0),
            "excluded_rows": matrix_payload.get("excluded_rows", []),
        },
        "method_definitions": [
            {
                "method": "univariate_numeric_effect_size",
                "description": "Absolute normalized mean gap between positive and negative target rows for numeric features.",
            },
            {
                "method": "univariate_categorical_rate_gap",
                "description": "Weighted deviation from baseline target rate across categorical feature values.",
            },
        ],
        "target_definitions": target_definitions,
        "targets": results,
        "warnings": sorted(set(overall_warnings)),
        "caveats": [
            "Offline-only association analysis; these rankings are not causal proof.",
            "Outputs must not be wired into online/runtime decisioning in this PR.",
            "Sparse coverage and class imbalance reduce confidence and should be reviewed manually.",
        ],
    }
    log_info(
        "offline_feature_importance_completed",
        target_count=len(results),
        warning_count=len(output["warnings"]),
        excluded_row_count=output["input_artifact"]["excluded_row_count"],
    )
    return output



def summarize_feature_importance(importance_payload: dict[str, Any]) -> str:
    lines = [
        "# Offline feature importance summary",
        "",
        "This artifact is **analysis-only** and **not for online decisioning**.",
        "Importance scores reflect association strength, not causal proof.",
        "",
        "## Input summary",
        f"- source: {importance_payload.get('input_artifact', {}).get('path', 'unknown')}",
        f"- usable rows: {importance_payload.get('input_artifact', {}).get('row_count', 0)}",
        f"- excluded rows: {importance_payload.get('input_artifact', {}).get('excluded_row_count', 0)}",
        f"- malformed rows: {importance_payload.get('input_artifact', {}).get('malformed_row_count', 0)}",
        "",
    ]

    if importance_payload.get("warnings"):
        lines.append("## Global warnings")
        for warning in importance_payload["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    for target in importance_payload.get("target_definitions", []):
        lines.append(f"## Target: {target.get('target_name')}")
        lines.append(f"- description: {target.get('description')}")
        lines.append(f"- sample_size: {target.get('sample_size', 0)}")
        lines.append(f"- positives: {target.get('positive_count', 0)}")
        lines.append(f"- negatives: {target.get('negative_count', 0)}")
        if target.get("warnings"):
            lines.append(f"- warnings: {', '.join(target['warnings'])}")
        matching = next(
            (item for item in importance_payload.get("targets", []) if item.get("target_name") == target.get("target_name")),
            None,
        )
        if not matching:
            lines.append("- no feature ranking available")
            lines.append("")
            continue
        lines.append("- top feature groups:")
        for group in matching.get("grouped_importance", [])[:5]:
            lines.append(
                "  - {group}: total={total:.4f} avg={avg:.4f} coverage={coverage:.2%} top={top}".format(
                    group=group.get("feature_group"),
                    total=float(group.get("importance_score_total", 0.0)),
                    avg=float(group.get("importance_score_avg", 0.0)),
                    coverage=float(group.get("coverage_ratio_avg", 0.0)),
                    top=", ".join(group.get("top_features", [])) or "n/a",
                )
            )
        lines.append("- top features:")
        for feature in matching.get("per_feature_importance", [])[:8]:
            lines.append(
                "  - #{rank} {name} [{group}] score={score:.4f} coverage={coverage:.2%} status={status} direction={direction}".format(
                    rank=int(feature.get("importance_rank", 0)),
                    name=feature.get("feature_name"),
                    group=feature.get("feature_group"),
                    score=float(feature.get("importance_score", 0.0)),
                    coverage=float(feature.get("coverage_ratio", 0.0)),
                    status=feature.get("status"),
                    direction=feature.get("direction_hint") or "n/a",
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"



def write_feature_importance_outputs(
    importance_payload: dict[str, Any],
    output_dir: str | Path,
    *,
    json_filename: str = "feature_importance.json",
    markdown_filename: str = "feature_importance_summary.md",
) -> dict[str, str]:
    target_dir = ensure_dir(output_dir)
    json_path = write_json(target_dir / json_filename, importance_payload)
    markdown_path = target_dir / markdown_filename
    markdown_path.write_text(summarize_feature_importance(importance_payload), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}
