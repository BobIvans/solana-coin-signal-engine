from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.wallet_clustering import (
    assign_wallet_cluster_ids,
    compute_bundle_wallet_clustering_score,
    compute_wallet_clustering_metrics,
    infer_wallet_cluster_keys,
)


def test_multi_cluster_fixture_has_lower_concentration_and_more_unique_clusters():
    participants = [
        {"wallet": "wallet_a", "funder": "funder_1"},
        {"wallet": "wallet_b", "funder": "funder_1"},
        {"wallet": "wallet_c", "funder": "funder_2"},
        {"wallet": "wallet_d", "funder": "funder_2"},
        {"wallet": "wallet_e", "funder": "funder_3"},
        {"wallet": "wallet_f", "funder": "funder_3"},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
    )

    assert metrics["cluster_concentration_ratio"] == 0.333333
    assert metrics["num_unique_clusters_first_60s"] == 3
    assert metrics["bundle_wallet_clustering_score"] == 0.3
    assert metrics["creator_in_cluster_flag"] is None
    assert metrics["linkage_status"] == "ok"
    assert metrics["shared_funder_link_score"] > 0
    assert metrics["linkage_risk_score"] <= 0.3


def test_single_cluster_fixture_has_high_concentration_ratio():
    participants = [
        {"wallet": "wallet_a", "funder": "shared_funder"},
        {"wallet": "wallet_b", "funder": "shared_funder"},
        {"wallet": "wallet_c", "funder": "shared_funder"},
        {"wallet": "wallet_d", "funder": "shared_funder"},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
    )

    assert metrics["cluster_concentration_ratio"] == 1.0
    assert metrics["num_unique_clusters_first_60s"] == 1
    assert metrics["bundle_wallet_clustering_score"] == 0.9
    assert metrics["shared_funder_link_score"] > 0


def test_creator_linked_fixture_sets_creator_in_cluster_flag():
    participants = [
        {"wallet": "creator_wallet", "funder": "shared_funder", "creator_linked": True},
        {"wallet": "wallet_a", "funder": "shared_funder", "creator_linked": True},
        {"wallet": "wallet_b", "funder": "shared_funder", "creator_linked": True},
        {"wallet": "wallet_c", "funder": "other_funder"},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        creator_wallet="creator_wallet",
        participant_wallets=["wallet_a", "wallet_b", "wallet_c"],
    )

    assert metrics["creator_in_cluster_flag"] is True
    assert metrics["cluster_concentration_ratio"] == 0.666667
    assert metrics["num_unique_clusters_first_60s"] == 1
    assert metrics["bundle_wallet_clustering_score"] == 0.766667
    assert metrics["creator_buyer_link_score"] > 0
    assert metrics["linkage_confidence"] >= 0.3


def test_missing_evidence_fixture_returns_none_safe_outputs():
    participants = [
        {"wallet": "wallet_a"},
        {"wallet": "wallet_b"},
        {"wallet": "wallet_c"},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
    )

    assert metrics["bundle_wallet_clustering_score"] is None
    assert metrics["cluster_concentration_ratio"] is None
    assert metrics["num_unique_clusters_first_60s"] is None
    assert metrics["creator_in_cluster_flag"] is None
    assert metrics["linkage_status"] == "partial"


def test_cluster_key_assignment_is_deterministic_for_repeated_group_pairs():
    participants = [
        {"wallet": "wallet_b", "group_id": ["slot:1", "slot:2"]},
        {"wallet": "wallet_a", "group_id": ["slot:1", "slot:2"]},
        {"wallet": "wallet_c", "group_id": ["slot:3"]},
    ]

    keys = infer_wallet_cluster_keys(participants)
    clusters = assign_wallet_cluster_ids(keys)

    assert keys["wallet_a"] == ["coappear:wallet_a|wallet_b"]
    assert keys["wallet_b"] == ["coappear:wallet_a|wallet_b"]
    assert clusters == {"wallet_a": "cluster_1", "wallet_b": "cluster_1"}
    assert compute_bundle_wallet_clustering_score(
        cluster_concentration_ratio=1.0,
        num_unique_clusters_first_60s=1,
        creator_in_cluster_flag=False,
    ) == 0.9
