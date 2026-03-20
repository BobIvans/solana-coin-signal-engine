from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.wallet_clustering import compute_wallet_clustering_metrics


class DummySettings:
    WALLET_GRAPH_ENABLED = True
    WALLET_GRAPH_EDGE_MIN_WEIGHT = 0.5
    PROCESSED_DATA_DIR = Path("./data/processed")
    WALLET_GRAPH_OUTPUT_PATH = Path("./data/processed/wallet_graph.json")
    WALLET_CLUSTER_OUTPUT_PATH = Path("./data/processed/wallet_clusters.json")
    WALLET_GRAPH_EVENTS_PATH = Path("./data/processed/wallet_graph_events.jsonl")


ORGANIC = [
    {"wallet": "wallet_a", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_b", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_c", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_d", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_e", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
    {"wallet": "wallet_f", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
]
SINGLE_CLUSTER = [
    {"wallet": "wallet_a", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": ["launch_alpha", "launch_beta"]},
    {"wallet": "wallet_b", "funder": "shared_funder", "group_id": ["slot:1"], "launch_id": ["launch_alpha", "launch_beta"]},
    {"wallet": "wallet_c", "funder": "shared_funder", "group_id": ["slot:2"], "launch_id": ["launch_alpha", "launch_beta"]},
    {"wallet": "wallet_d", "funder": "shared_funder", "group_id": ["slot:2"], "launch_id": ["launch_alpha", "launch_beta"]},
]
CREATOR_LINKED = [
    {"wallet": "creator_wallet", "creator_linked": True, "creator_wallet": "creator_wallet", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_a", "funder": "shared", "creator_linked": True, "creator_wallet": "creator_wallet", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_b", "funder": "shared", "creator_linked": True, "creator_wallet": "creator_wallet", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_c", "funder": "other", "group_id": ["slot:3"], "launch_id": "launch_beta"},
]
SPARSE = [
    {"wallet": "wallet_a", "funder": "shared"},
    {"wallet": "wallet_b", "funder": "shared"},
    {"wallet": "wallet_c"},
    {"wallet": "wallet_d"},
]
MALFORMED = [
    {"wallet": "wallet_a", "timestamp": "not-a-time"},
    {"wallet": "wallet_b", "group_id": None},
    {"wallet": None, "funder": "shared"},
]


def test_fixture_1_organic_multi_cluster_uses_graph_origin():
    metrics = compute_wallet_clustering_metrics(ORGANIC, participant_wallets=[item["wallet"] for item in ORGANIC], settings=DummySettings())

    assert metrics["num_unique_clusters_first_60s"] >= 3
    assert metrics["cluster_concentration_ratio"] == 0.333333
    assert metrics["creator_in_cluster_flag"] is None
    assert metrics["cluster_metric_origin"] == "graph_evidence"


def test_fixture_2_single_cluster_dev_farm_is_high_concentration():
    metrics = compute_wallet_clustering_metrics(SINGLE_CLUSTER, participant_wallets=[item["wallet"] for item in SINGLE_CLUSTER], settings=DummySettings())

    assert metrics["cluster_concentration_ratio"] == 1.0
    assert metrics["num_unique_clusters_first_60s"] == 1
    assert metrics["bundle_wallet_clustering_score"] == 0.9
    assert metrics["cluster_metric_origin"] == "graph_evidence"


def test_fixture_3_creator_linked_buyers_sets_creator_flag_from_graph():
    metrics = compute_wallet_clustering_metrics(
        CREATOR_LINKED,
        creator_wallet="creator_wallet",
        participant_wallets=["wallet_a", "wallet_b", "wallet_c"],
        settings=DummySettings(),
    )

    assert metrics["creator_in_cluster_flag"] is True
    assert metrics["cluster_metric_origin"] == "graph_evidence"
    assert metrics["cluster_evidence_confidence"] <= 0.95


def test_fixture_4_sparse_graph_uses_heuristic_fallback():
    metrics = compute_wallet_clustering_metrics(SPARSE, participant_wallets=[item["wallet"] for item in SPARSE], settings=DummySettings())

    assert metrics["cluster_metric_origin"] == "heuristic_fallback"
    assert metrics["cluster_evidence_source"] == "heuristic_keys"


def test_fixture_5_malformed_inputs_degrade_safely_without_exception():
    metrics = compute_wallet_clustering_metrics(MALFORMED, participant_wallets=["wallet_a", "wallet_b"], settings=DummySettings())

    assert metrics["cluster_metric_origin"] in {"heuristic_fallback", "missing"}
    assert metrics["bundle_wallet_clustering_score"] is None


def test_fixture_6_stable_id_rerun_via_graph_path_is_deterministic():
    first = compute_wallet_clustering_metrics(ORGANIC, participant_wallets=[item["wallet"] for item in ORGANIC], settings=DummySettings())
    second = compute_wallet_clustering_metrics(list(reversed(ORGANIC)), participant_wallets=[item["wallet"] for item in reversed(ORGANIC)], settings=DummySettings())

    assert first["dominant_cluster_id"] == second["dominant_cluster_id"]


def test_explicit_artifact_input_is_required_to_use_persisted_clusters(tmp_path: Path):
    stale_clusters = {
        "wallet_to_cluster": {"wallet_a": "cluster_stale", "wallet_b": "cluster_stale", "wallet_c": "cluster_stale"},
        "clusters": [{"cluster_id": "cluster_stale", "cluster_confidence": 0.99}],
        "summary": {"cluster_count": 1},
    }
    settings = DummySettings()
    settings.PROCESSED_DATA_DIR = tmp_path
    settings.WALLET_GRAPH_OUTPUT_PATH = tmp_path / "wallet_graph.json"
    settings.WALLET_CLUSTER_OUTPUT_PATH = tmp_path / "wallet_clusters.json"
    settings.WALLET_GRAPH_EVENTS_PATH = tmp_path / "wallet_graph_events.jsonl"
    settings.WALLET_CLUSTER_OUTPUT_PATH.write_text(__import__("json").dumps(stale_clusters), encoding="utf-8")

    metrics = compute_wallet_clustering_metrics(
        ORGANIC,
        participant_wallets=[item["wallet"] for item in ORGANIC],
        settings=settings,
        artifact_scope={"token_address": "tok-1", "pair_address": "pair-1"},
    )

    assert metrics["cluster_metric_origin"] == "graph_evidence"
    assert metrics["dominant_cluster_id"] != "cluster_stale"


def test_explicit_scoped_artifact_is_used_when_scope_matches():
    scoped_clusters = {
        "metadata": {"token_address": "tok-1", "pair_address": "pair-1"},
        "wallet_to_cluster": {
            "wallet_a": "cluster_scoped",
            "wallet_b": "cluster_scoped",
            "wallet_c": "cluster_other",
            "wallet_d": "cluster_other",
            "wallet_e": "cluster_third",
            "wallet_f": "cluster_third",
        },
        "clusters": [
            {"cluster_id": "cluster_scoped", "cluster_confidence": 0.91},
            {"cluster_id": "cluster_other", "cluster_confidence": 0.82},
            {"cluster_id": "cluster_third", "cluster_confidence": 0.79},
        ],
        "summary": {"cluster_count": 3},
    }

    metrics = compute_wallet_clustering_metrics(
        ORGANIC,
        participant_wallets=[item["wallet"] for item in ORGANIC],
        settings=DummySettings(),
        clusters_artifact=scoped_clusters,
        artifact_scope={"token_address": "tok-1", "pair_address": "pair-1"},
    )

    assert metrics["cluster_metric_origin"] == "graph_evidence"
    assert metrics["cluster_evidence_source"] == "persistent_artifact"
    assert metrics["dominant_cluster_id"] == "cluster_other"


def test_explicit_scoped_artifact_is_ignored_when_scope_mismatches():
    mismatched_clusters = {
        "metadata": {"token_address": "tok-other", "pair_address": "pair-other"},
        "wallet_to_cluster": {
            "wallet_a": "cluster_stale",
            "wallet_b": "cluster_stale",
            "wallet_c": "cluster_stale",
            "wallet_d": "cluster_stale",
            "wallet_e": "cluster_stale",
            "wallet_f": "cluster_stale",
        },
        "clusters": [{"cluster_id": "cluster_stale", "cluster_confidence": 0.99}],
        "summary": {"cluster_count": 1},
    }

    metrics = compute_wallet_clustering_metrics(
        ORGANIC,
        participant_wallets=[item["wallet"] for item in ORGANIC],
        settings=DummySettings(),
        clusters_artifact=mismatched_clusters,
        artifact_scope={"token_address": "tok-1", "pair_address": "pair-1"},
    )

    assert metrics["cluster_metric_origin"] == "graph_evidence"
    assert metrics["cluster_evidence_source"] == "inline_graph_builder"
    assert metrics["dominant_cluster_id"] != "cluster_stale"


class HeuristicOnlySettings(DummySettings):
    WALLET_GRAPH_ENABLED = False


def test_windowed_heuristic_fallback_ignores_late_out_of_window_wallets():
    participants = [
        {"wallet": "wallet_a", "group_id": ["slot:1", "slot:2"], "timestamp": 1000},
        {"wallet": "wallet_b", "group_id": ["slot:1", "slot:2"], "timestamp": 1010},
        {"wallet": "wallet_c", "group_id": ["slot:9", "slot:10"], "timestamp": 1700},
        {"wallet": "wallet_d", "group_id": ["slot:9", "slot:10"], "timestamp": 1710},
    ]

    metrics = compute_wallet_clustering_metrics(
        participants,
        participant_wallets=[item["wallet"] for item in participants],
        settings=HeuristicOnlySettings(),
        artifact_scope={"bundle_window_anchor_ts": 1000, "bundle_window_sec": 60},
    )

    assert metrics["cluster_metric_origin"] == "heuristic_fallback"
    assert metrics["cluster_evidence_source"] == "heuristic_keys"
    assert metrics["cluster_concentration_ratio"] == 1.0
    assert metrics["num_unique_clusters_first_60s"] == 1
