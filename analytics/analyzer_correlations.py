"""Correlation analysis for post-run metrics -> PnL relationships."""

from __future__ import annotations

import math
from typing import Any

from config.settings import Settings


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    den_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
    den_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _rank(values: list[float]) -> list[float]:
    ordered = sorted((value, idx) for idx, value in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[ordered[k][1]] = avg_rank
        i = j + 1
    return ranks


def _spearman(x: list[float], y: list[float]) -> float:
    return _pearson(_rank(x), _rank(y))


def _clip_series(values: list[float], clip_pct: float) -> list[float]:
    if not values or clip_pct <= 0:
        return values
    ordered = sorted(values)
    low_idx = int(len(values) * clip_pct)
    high_idx = max(low_idx, int(len(values) * (1 - clip_pct)) - 1)
    low = ordered[min(low_idx, len(ordered) - 1)]
    high = ordered[min(high_idx, len(ordered) - 1)]
    return [min(max(v, low), high) for v in values]


def _confidence_label(abs_corr: float) -> str:
    if abs_corr >= 0.5:
        return "high"
    if abs_corr >= 0.25:
        return "medium"
    return "low"


def compute_metric_correlations(
    closed_positions: list[dict[str, Any]], metrics: list[str], target: str, settings: Settings
) -> list[dict[str, Any]]:
    min_sample = int(settings.POST_RUN_MIN_TRADES_FOR_CORRELATION)
    clip_pct = float(settings.POST_RUN_OUTLIER_CLIP_PCT)

    output: list[dict[str, Any]] = []
    for metric in metrics:
        pairs: list[tuple[float, float]] = []
        for row in closed_positions:
            target_value = row.get(target)
            metric_value = row.get(metric)
            if target_value is None:
                continue
            if metric_value is None:
                metric_value = row.get("entry_snapshot", {}).get(metric)
            if metric_value is None:
                continue
            pairs.append((float(metric_value), float(target_value)))

        sample = len(pairs)
        if sample < min_sample:
            output.append(
                {
                    "metric": metric,
                    "sample_size": sample,
                    "status": "insufficient_sample",
                    "pearson_corr": 0.0,
                    "spearman_corr": 0.0,
                    "direction": "flat",
                    "confidence_label": "insufficient_sample",
                }
            )
            continue

        x = [p[0] for p in pairs]
        y = [p[1] for p in pairs]
        if clip_pct > 0:
            x = _clip_series(x, clip_pct)
            y = _clip_series(y, clip_pct)

        pearson = _pearson(x, y)
        spearman = _spearman(x, y)
        avg = (pearson + spearman) / 2

        output.append(
            {
                "metric": metric,
                "sample_size": sample,
                "status": "ok",
                "pearson_corr": pearson,
                "spearman_corr": spearman,
                "direction": "positive" if avg > 0.05 else ("negative" if avg < -0.05 else "flat"),
                "confidence_label": _confidence_label(abs(avg)),
            }
        )

    return output
