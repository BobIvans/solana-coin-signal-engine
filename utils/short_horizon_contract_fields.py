"""Shared short-horizon enrichment contract field helpers."""

from __future__ import annotations

from typing import Any

SHORT_HORIZON_SIGNAL_FIELDS = [
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "smart_wallet_dispersion_score",
    "x_author_velocity_5m",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
]


def copy_short_horizon_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy short-horizon contract fields with optional fallback lookup."""

    output: dict[str, Any] = {}
    fallback = fallback or {}
    for field in SHORT_HORIZON_SIGNAL_FIELDS:
        if field in source:
            output[field] = source.get(field)
        else:
            output[field] = fallback.get(field)
    return output
