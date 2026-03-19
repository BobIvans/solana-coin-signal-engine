"""Markdown report writer for post-run analyzer outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _section(title: str) -> str:
    return f"\n## {title}\n"


def _fmt_float(value: Any) -> str:
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

    lines += [_section("strongest positive/negative feature slices"), "- strongest positive slices:"]
    _append_slice_lines(lines, summary.get("top_positive_feature_slices", []))
    lines.append("- strongest negative slices:")
    _append_slice_lines(lines, summary.get("top_negative_feature_slices", []))

    lines += [_section("top threshold-adjustment suggestions")]
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

    lines += [_section("caveats / sample-size warnings")]
    for warning in summary.get("warnings", []):
        lines.append(f"- {warning}")

    Path(output_path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
