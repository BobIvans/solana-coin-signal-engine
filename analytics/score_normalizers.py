"""Deterministic numeric normalizers for unified scoring."""

from __future__ import annotations

import math


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_unit_interval(value: float | None) -> float:
    """Normalize already unit-scaled value into [0, 1]."""
    if value is None:
        return 0.0
    try:
        return _clamp01(float(value))
    except (TypeError, ValueError):
        return 0.0


def normalize_capped(value: float | None, low: float, high: float) -> float:
    """Normalize linear bounded values into [0, 1]."""
    if value is None:
        return 0.0
    if high <= low:
        return 0.0
    try:
        ratio = (float(value) - low) / (high - low)
    except (TypeError, ValueError):
        return 0.0
    return _clamp01(ratio)


def normalize_inverse(value: float | None, good: float, bad: float) -> float:
    """Inverse-risk transform where lower values are better."""
    if value is None:
        return 0.0
    if bad == good:
        return 0.0
    try:
        ratio = (bad - float(value)) / (bad - good)
    except (TypeError, ValueError):
        return 0.0
    return _clamp01(ratio)


def normalize_log_scaled(value: float | None, low: float, high: float) -> float:
    """Log-scaled normalization for long-tail positive metrics."""
    if value is None:
        return 0.0
    if low <= 0 or high <= 0 or high <= low:
        return 0.0
    try:
        val = float(value)
    except (TypeError, ValueError):
        return 0.0
    val = max(low, min(high, val))
    denom = math.log(high) - math.log(low)
    if denom <= 0:
        return 0.0
    return _clamp01((math.log(val) - math.log(low)) / denom)
