"""Slice helpers for post-run analyzer."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _fmt_bucket(low: float, high: float | None) -> str:
    if high is None:
        return f"{low:.2f}+"
    return f"{low:.2f}-{high:.2f}"


def _metric_summary(values: list[dict[str, Any]]) -> dict[str, float]:
    size = len(values)
    wins = sum(1 for row in values if float(row.get("net_pnl_sol", 0.0)) > 0)
    avg_pnl = sum(float(row.get("net_pnl_pct", 0.0)) for row in values) / size if size else 0.0
    return {"count": size, "winrate": (wins / size if size else 0.0), "avg_net_pnl_pct": avg_pnl}


def slice_positions(closed_positions: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in closed_positions:
        grouped[str(position.get(key, "unknown"))].append(position)
    return {bucket: _metric_summary(items) for bucket, items in grouped.items()}


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
    return {bucket: _metric_summary(items) for bucket, items in grouped.items()}
