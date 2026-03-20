from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.wallet_clustering import (
    assign_wallet_cluster_ids,
    compute_bundle_wallet_clustering_score,
    compute_wallet_clustering_metrics,
    infer_wallet_cluster_keys,
    resolve_wallet_cluster_assignments,
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
    assert metrics["cluster_metric_origin"] == "missing"
    assert metrics["linkage_status"] in {"partial", "missing"}


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


def test_graph_windowing_excludes_later_participants_from_cluster_metrics():
    participants = [
        {"wallet": "wallet_a", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "timestamp": 1000},
        {"wallet": "wallet_b", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "timestamp": 1010},
        {"wallet": "wallet_c", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "timestamp": 1020},
        {"wallet": "wallet_d", "funder": "retail_1", "group_id": ["slot:9"], "launch_id": "launch_late", "timestamp": 1700},
        {"wallet": "wallet_e", "funder": "retail_2", "group_id": ["slot:10"], "launch_id": "launch_late", "timestamp": 1710},
        {"wallet": "wallet_f", "funder": "retail_3", "group_id": ["slot:11"], "launch_id": "launch_late", "timestamp": 1720},
        {"wallet": "wallet_g", "funder": "retail_4", "group_id": ["slot:12"], "launch_id": "launch_late", "timestamp": 1730},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
        artifact_scope={"bundle_window_anchor_ts": 1000, "bundle_window_sec": 60},
    )

    assert metrics["cluster_concentration_ratio"] == 1.0
    assert metrics["num_unique_clusters_first_60s"] == 1
    assert metrics["graph_cluster_id_count"] == 1
    assert metrics["dominant_cluster_id"] is not None


def test_graph_windowing_drops_missing_timestamps_from_strict_path():
    participants = [
        {"wallet": "wallet_a", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "timestamp": 1000},
        {"wallet": "wallet_b", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "timestamp": 1015},
        {"wallet": "wallet_c", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
        {"wallet": "wallet_d", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": "launch_alpha", "time": "not-a-timestamp"},
    ]

    resolved = resolve_wallet_cluster_assignments(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
        artifact_scope={"bundle_window_anchor_ts": 1000, "bundle_window_sec": 60},
    )

    assert set(resolved["cluster_ids_by_wallet"]) == {"wallet_a", "wallet_b"}
    assert "window_filter_dropped_missing_timestamp:2" in resolved["warnings"]


def test_graph_windowing_warns_when_scope_unavailable():
    participants = [
        {"wallet": "wallet_a", "funder": "shared_funder", "timestamp": 1000},
        {"wallet": "wallet_b", "funder": "shared_funder", "timestamp": 1010},
    ]

    resolved = resolve_wallet_cluster_assignments(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
    )

    assert "window_scope_unavailable" in resolved["warnings"]
