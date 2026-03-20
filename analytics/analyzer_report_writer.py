"""Markdown report writer for post-run analyzer outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _section(title: str) -> str:
    return f"\n## {title}\n"


def _fmt_float(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _append_slice_lines(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        lines.append("- unavailable")
        return
    for row in rows:
        lines.append(
            "- {slice}: count={count} avg_net_pnl_pct={avg} winrate={winrate}".format(
                slice=row.get("slice", "unknown"),
                count=row.get("count", 0),
                avg=_fmt_float(float(row.get("avg_net_pnl_pct", 0.0))),
                winrate=_fmt_float(float(row.get("winrate", 0.0))),
            )
        )


def _append_numeric_summary(lines: list[str], label: str, summary: dict[str, Any]) -> None:
    lines.append(
        "- {label}: count={count} avg={avg} median={median} min={minv} max={maxv}".format(
            label=label,
            count=summary.get("count", 0),
            avg=_fmt_float(summary.get("avg")),
            median=_fmt_float(summary.get("median")),
            minv=_fmt_float(summary.get("min")),
            maxv=_fmt_float(summary.get("max")),
        )
    )


def _append_rich_slice_group(lines: list[str], title: str, group: dict[str, Any]) -> None:
    lines += [_section(title)]
    if not group:
        lines.append("- unavailable")
        return
    for slice_name, payload in group.items():
        if not isinstance(payload, dict):
            continue
        sample_size = payload.get("sample_size", 0)
        status = payload.get("status", "unknown")
        confidence = payload.get("confidence", "unknown")
        expectancy = payload.get("expectancy", payload.get("expectancy_gap", payload.get("trend_expectancy")))
        hint = payload.get("recommendation_hint")
        interpretation = payload.get("interpretation", "")
        warnings = payload.get("warnings", [])
        lines.append(
            f"- {slice_name}: sample={sample_size} status={status} confidence={confidence} expectancy={_fmt_float(expectancy)}"
        )
        if interpretation:
            lines.append(f"  - note: {interpretation}")
        if hint:
            lines.append(f"  - recommendation_hint: {hint}")
        if warnings:
            lines.append(f"  - warnings: {', '.join(str(w) for w in warnings)}")


def write_markdown_report(summary: dict[str, Any], recommendations: dict[str, Any], output_path: str) -> None:
    lines: list[str] = ["# Post-run analyzer report", ""]

    lines += [_section("overview"), f"- as_of: {summary.get('as_of', '')}", f"- closed positions: {summary.get('total_positions_closed', 0)}"]
    lines += [
        _section("portfolio results"),
        f"- realized_pnl_sol: {summary.get('realized_pnl_sol', 0.0):.6f}",
        f"- unrealized_pnl_sol: {summary.get('unrealized_pnl_sol', 0.0):.6f}",
        f"- winrate_total: {summary.get('winrate_total', 0.0):.4f}",
        f"- profit_factor_total: {summary.get('profit_factor_total', 0.0):.4f}",
    ]

    lines += [_section("regime comparison"), "- winrate_by_regime:"]
    for regime, value in summary.get("winrate_by_regime", {}).items():
        lines.append(f"  - {regime}: {value:.4f}")

    lines += [_section("exit reason analysis"), "- exit_reason_distribution:"]
    for reason, count in summary.get("exit_reason_distribution", {}).items():
        lines.append(f"  - {reason}: {count}")

    lines += [_section("friction analysis"), "- friction_summary:"]
    for key, value in summary.get("friction_summary", {}).items():
        if isinstance(value, float):
            lines.append(f"  - {key}: {value:.6f}")
        else:
            lines.append(f"  - {key}: {value}")

    lines += [_section("correlation analysis"), "- metric_correlations:"]
    for row in summary.get("metric_correlations", []):
        lines.append(
            f"  - {row.get('metric')}: status={row.get('status')} pearson={row.get('pearson_corr', 0.0):.4f} spearman={row.get('spearman_corr', 0.0):.4f} sample={row.get('sample_size', 0)}"
        )

    lines += [_section("bundle / cluster feature insights")]
    if summary.get("matrix_analysis_available"):
        lines.append(f"- matrix rows used: {summary.get('matrix_row_count', 0)}")
        for row in summary.get("bundle_cluster_correlations", [])[:10]:
            lines.append(
                f"- {row.get('metric')}: status={row.get('status')} pearson={row.get('pearson_corr', 0.0):.4f} spearman={row.get('spearman_corr', 0.0):.4f} sample={row.get('sample_size', 0)}"
            )
    else:
        lines.append("- trade_feature_matrix.jsonl unavailable; legacy analyzer mode used")

    lines += [_section("regime misclassification insights")]
    trend_failed = summary.get("trend_failure_summary", {})
    scalp_missed = summary.get("scalp_missed_trend_summary", {})
    regime_confusion = summary.get("regime_confusion_summary", {})
    lines.append(
        f"- TREND promoted but failed fast: count={trend_failed.get('count', 0)} avg_net_pnl_pct={float(trend_failed.get('avg_net_pnl_pct', 0.0)):.4f} avg_regime_confidence={float(trend_failed.get('avg_regime_confidence', 0.0)):.4f}"
    )
    lines.append(
        f"- SCALP should have been TREND: count={scalp_missed.get('count', 0)} avg_net_pnl_pct={float(scalp_missed.get('avg_net_pnl_pct', 0.0)):.4f} avg_mfe_capture_gap_pct={float(scalp_missed.get('avg_mfe_capture_gap_pct', 0.0)):.4f}"
    )
    for name, bucket in regime_confusion.get("regime_confidence_buckets", {}).items():
        lines.append(
            f"- {name}: count={bucket.get('count', 0)} avg_net_pnl_pct={float(bucket.get('avg_net_pnl_pct', 0.0)):.4f} winrate={float(bucket.get('winrate', 0.0)):.4f}"
        )

    lines += [_section("calibration-only outcome summaries")]
    scalp_vs_trend = summary.get("scalp_vs_trend_outcome_summary", {})
    for regime in ("SCALP", "TREND"):
        regime_summary = scalp_vs_trend.get(regime, {})
        lines.append(f"- {regime}: count={regime_summary.get('count', 0)}")
        for field in ("time_to_first_profit_sec", "mfe_pct_240s", "mae_pct_240s", "trend_survival_15m", "trend_survival_60m"):
            _append_numeric_summary(lines, f"{regime}.{field}", regime_summary.get(field, {}))

    lines.append("- overall time_to_first_profit_summary:")
    time_to_first_profit = summary.get("time_to_first_profit_summary", {})
    _append_numeric_summary(lines, "overall", time_to_first_profit.get("overall", {}))
    for regime, regime_summary in time_to_first_profit.get("by_regime", {}).items():
        _append_numeric_summary(lines, f"by_regime.{regime}", regime_summary)

    lines.append("- mfe_mae_summary:")
    for field, field_summary in summary.get("mfe_mae_summary", {}).items():
        _append_numeric_summary(lines, field, field_summary)

    lines.append("- trend_survival_summary:")
    for field, field_summary in summary.get("trend_survival_summary", {}).items():
        _append_numeric_summary(lines, field, field_summary)

    lines += [_section("strongest positive/negative feature slices"), "- strongest positive slices:"]
    _append_slice_lines(lines, summary.get("top_positive_feature_slices", []))
    lines.append("- strongest negative slices:")
    _append_slice_lines(lines, summary.get("top_negative_feature_slices", []))

    analyzer_slices = recommendations.get("analyzer_slices", {})
    slice_groups = analyzer_slices.get("slice_groups", {}) if isinstance(analyzer_slices, dict) else {}
    _append_rich_slice_group(lines, "regime diagnostics", slice_groups.get("regime", {}))
    _append_rich_slice_group(lines, "cluster/bundle diagnostics", slice_groups.get("cluster_bundle", {}))
    _append_rich_slice_group(lines, "continuation diagnostics", slice_groups.get("continuation", {}))
    _append_rich_slice_group(lines, "degraded X diagnostics", slice_groups.get("degraded_x", {}))
    _append_rich_slice_group(lines, "evidence quality diagnostics", slice_groups.get("evidence_quality", analyzer_slices.get("evidence_quality_slices", {})))
    _append_rich_slice_group(lines, "exit/failure diagnostics", slice_groups.get("exit_failure", {}))

    lines += [_section("key conservative recommendations")]
    if recommendations.get("recommendations"):
        for rec in recommendations.get("recommendations", []):
            lines.append(
                f"- [{rec.get('type')}] {rec.get('target')}: {rec.get('suggested_action')} (confidence={rec.get('confidence')}) — {rec.get('reason')}"
            )
    else:
        lines.append("- unavailable")

    lines += [_section("recommendations")]
    for rec in recommendations.get("recommendations", []):
        lines.append(f"- [{rec.get('type')}] {rec.get('target')}: {rec.get('suggested_action')} (confidence={rec.get('confidence')})")

    lines += [_section("sample-size warnings")]
    slice_inputs = analyzer_slices.get("recommendation_inputs", {}) if isinstance(analyzer_slices, dict) else {}
    low_sample = slice_inputs.get("low_sample_slices", [])
    if low_sample:
        for item in low_sample:
            lines.append(f"- low-confidence slice: {item}")
    else:
        lines.append("- no analyzer-slice-specific sample warnings")

    lines += [_section("caveats / sample-size warnings")]
    for warning in summary.get("warnings", []):
        lines.append(f"- {warning}")

    Path(output_path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
