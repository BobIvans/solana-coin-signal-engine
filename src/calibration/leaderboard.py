"""Leaderboard assembly and ranking."""

from __future__ import annotations


def compare_to_baseline(candidate: dict, baseline: dict, primary_metric: str = "validation_expectancy") -> bool:
    metric_name = primary_metric.replace("validation_", "")
    c_value = float(candidate.get("validation", {}).get(metric_name, 0.0))
    b_value = float(baseline.get("validation", {}).get(metric_name, 0.0))
    return c_value > b_value


def rank_candidates(results: list[dict], primary_metric: str) -> list[dict]:
    metric_name = primary_metric.replace("validation_", "")
    ranked = sorted(
        results,
        key=lambda row: (
            float(row.get("validation", {}).get(metric_name, 0.0)),
            float(row.get("validation", {}).get("median_pnl_pct", 0.0)),
            float(row.get("validation", {}).get("winrate", 0.0)),
            row.get("candidate_id", ""),
        ),
        reverse=True,
    )
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
    return ranked
