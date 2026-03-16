"""Markdown report writer for post-run analyzer outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _section(title: str) -> str:
    return f"\n## {title}\n"


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

    lines += [_section("recommendations")]
    for rec in recommendations.get("recommendations", []):
        lines.append(f"- [{rec.get('type')}] {rec.get('target')}: {rec.get('suggested_action')} (confidence={rec.get('confidence')})")

    lines += [_section("caveats / sample-size warnings")]
    for warning in summary.get("warnings", []):
        lines.append(f"- {warning}")

    Path(output_path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
