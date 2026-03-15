"""Developer early-sell risk checks."""

from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def check_dev_risk(token_ctx: dict, settings: Any) -> dict[str, Any]:
    pressure = _as_float(token_ctx.get("dev_sell_pressure_5m"))
    confidence = _as_float(token_ctx.get("dev_wallet_confidence_score", 1.0))

    flags: list[str] = []
    warnings: list[str] = []

    risk = 0.0
    if pressure >= settings.RUG_DEV_SELL_PRESSURE_HARD:
        risk = 0.9
        flags.append("dev_sell_pressure_hard")
    elif pressure >= settings.RUG_DEV_SELL_PRESSURE_WARN:
        risk = 0.45
        flags.append("dev_sell_pressure_warn")

    if confidence < 0.5:
        warnings.append("dev_wallet_low_confidence")

    return {
        "dev_risk": round(risk, 4),
        "dev_flags": flags,
        "dev_warnings": warnings,
    }
