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

BUNDLE_PROVENANCE_FIELDS = [
    "bundle_evidence_status",
    "bundle_evidence_source",
    "bundle_evidence_confidence",
    "bundle_evidence_warning",
    "bundle_metric_origin",
]

CLUSTER_PROVENANCE_FIELDS = [
    "cluster_evidence_status",
    "cluster_evidence_source",
    "cluster_evidence_confidence",
    "cluster_metric_origin",
    "graph_cluster_id_count",
    "graph_cluster_coverage_ratio",
    "creator_cluster_id",
    "dominant_cluster_id",
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


def copy_bundle_provenance_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy additive bundle provenance fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(BUNDLE_PROVENANCE_FIELDS, source, fallback)


def copy_cluster_provenance_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy additive cluster provenance fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(CLUSTER_PROVENANCE_FIELDS, source, fallback)


ALL_BUNDLE_EVIDENCE_FIELDS = [*BUNDLE_CONTRACT_FIELDS, *BUNDLE_PROVENANCE_FIELDS]
ALL_CLUSTER_EVIDENCE_FIELDS = [
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "creator_in_cluster_flag",
    *CLUSTER_PROVENANCE_FIELDS,
]
ALL_BUNDLE_LINKAGE_CONTRACT_FIELDS = [
    *BUNDLE_CONTRACT_FIELDS,
    *BUNDLE_PROVENANCE_FIELDS,
    *CLUSTER_PROVENANCE_FIELDS,
    *LINKAGE_CONTRACT_FIELDS,
]


def copy_bundle_and_linkage_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy both bundle/cluster and linkage contract fields with optional fallback lookup."""

    fallback = fallback or {}
    return _copy_fields(ALL_BUNDLE_LINKAGE_CONTRACT_FIELDS, source, fallback)
