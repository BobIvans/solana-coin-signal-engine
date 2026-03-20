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

CONTINUATION_METADATA_FIELDS = [
    "continuation_status",
    "continuation_warning",
    "continuation_confidence",
    "continuation_metric_origin",
    "continuation_coverage_ratio",
    "continuation_inputs_status",
    "continuation_warnings",
    "continuation_available_evidence",
    "continuation_missing_evidence",
]


def copy_short_horizon_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy short-horizon metric fields with optional fallback lookup."""

    output: dict[str, Any] = {}
    fallback = fallback or {}
    for field in SHORT_HORIZON_SIGNAL_FIELDS:
        if field in source:
            output[field] = source.get(field)
        else:
            output[field] = fallback.get(field)
    return output


def copy_continuation_metadata_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy additive continuation provenance/status fields with optional fallback lookup."""

    output: dict[str, Any] = {}
    fallback = fallback or {}
    for field in CONTINUATION_METADATA_FIELDS:
        if field in source:
            output[field] = source.get(field)
        else:
            output[field] = fallback.get(field)
    return output
