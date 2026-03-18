"""Shared bundle/cluster contract field helpers."""

from __future__ import annotations

from typing import Any

BUNDLE_CONTRACT_FIELDS = [
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
    "bundle_composition_dominant",
    "bundle_tip_efficiency",
    "bundle_failure_retry_pattern",
    "cross_block_bundle_correlation",
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "creator_in_cluster_flag",
]


def copy_bundle_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy bundle/cluster contract fields with optional fallback lookup."""

    output: dict[str, Any] = {}
    fallback = fallback or {}
    for field in BUNDLE_CONTRACT_FIELDS:
        if field in source:
            output[field] = source.get(field)
        else:
            output[field] = fallback.get(field)
    return output
