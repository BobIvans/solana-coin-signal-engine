"""Shared bundle/cluster and linkage contract field helpers."""

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

LINKAGE_CONTRACT_FIELDS = [
    "creator_dev_link_score",
    "creator_buyer_link_score",
    "dev_buyer_link_score",
    "shared_funder_link_score",
    "creator_cluster_link_score",
    "cluster_dev_link_score",
    "linkage_risk_score",
    "creator_funder_overlap_count",
    "buyer_funder_overlap_count",
    "funder_overlap_count",
    "linkage_reason_codes",
    "linkage_confidence",
    "linkage_metric_origin",
    "linkage_status",
    "linkage_warning",
]


def _copy_fields(fields: list[str], source: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in fields:
        if field in source:
            output[field] = source.get(field)
        else:
            output[field] = fallback.get(field)
    return output


def copy_bundle_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy bundle/cluster contract fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(BUNDLE_CONTRACT_FIELDS, source, fallback)


def copy_linkage_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy linkage contract fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(LINKAGE_CONTRACT_FIELDS, source, fallback)


ALL_BUNDLE_LINKAGE_CONTRACT_FIELDS = [*BUNDLE_CONTRACT_FIELDS, *LINKAGE_CONTRACT_FIELDS]


def copy_bundle_and_linkage_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy both bundle/cluster and linkage contract fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(ALL_BUNDLE_LINKAGE_CONTRACT_FIELDS, source, fallback)
