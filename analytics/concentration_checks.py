"""Holder concentration risk checks based on top1/top20 shares only."""

from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def check_concentration(token_ctx: dict, settings: Any) -> dict[str, Any]:
    top1 = _as_float(token_ctx.get("top1_holder_share"))
    top20 = _as_float(token_ctx.get("top20_holder_share"))

    penalty = 0.0
    flags: list[str] = []

    if top1 > settings.RUG_TOP1_HOLDER_HARD_MAX:
        penalty += 0.5
        flags.append("top1_high")
    elif top1 > settings.RUG_TOP1_HOLDER_HARD_MAX * 0.75:
        penalty += 0.2
        flags.append("top1_elevated")

    if top20 > settings.RUG_TOP20_HOLDER_HARD_MAX:
        penalty += 0.4
        flags.append("top20_high")
    elif top20 > settings.RUG_TOP20_HOLDER_HARD_MAX * 0.8:
        penalty += 0.15
        flags.append("top20_elevated")

    if "top1_high" in flags and "top20_high" not in flags:
        penalty += 0.1
        flags.append("top1_top20_shape_risk")

    return {
        "concentration_penalty": round(min(1.0, penalty), 4),
        "concentration_flags": flags,
    }
