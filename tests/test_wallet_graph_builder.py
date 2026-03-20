from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.wallet_graph_builder import build_wallet_graph, derive_wallet_clusters


ORGANIC_PARTICIPANTS = [
    {"wallet": "wallet_a", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_b", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_c", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_d", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_e", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
    {"wallet": "wallet_f", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
]


def test_build_wallet_graph_emits_deterministic_edges_with_provenance():
    graph = build_wallet_graph(ORGANIC_PARTICIPANTS, metadata={"token_address": "tok-1"})

    assert graph["metadata"]["contract_version"] == "wallet_graph.v1"
    assert graph["summary"]["node_count"] == 6
    assert graph["summary"]["edge_count"] == 3
    assert graph["edges"][0]["provenance"][0]["evidence_type"] in {"co_bundle_window", "same_launch", "shared_funder"}


def test_derive_wallet_clusters_produces_stable_cluster_ids_across_runs():
    first = derive_wallet_clusters(build_wallet_graph(ORGANIC_PARTICIPANTS))
    second = derive_wallet_clusters(build_wallet_graph(list(reversed(ORGANIC_PARTICIPANTS))))

    assert first["wallet_to_cluster"] == second["wallet_to_cluster"]
    assert first["summary"]["cluster_count"] == 3


def test_malformed_graph_inputs_are_filtered_without_crash():
    graph = {
        "nodes": [{"wallet": "wallet_a"}, {"wallet": "wallet_b"}, {"wallet": ""}],
        "edges": [
            {"source": "wallet_a", "target": "wallet_b", "weight": 0.8, "provenance": [{"evidence_type": "shared_funder", "weight": 0.8}]},
            {"source": "wallet_a", "target": None, "weight": 0.9, "provenance": []},
        ],
        "warnings": ["raw_warning"],
    }

    clusters = derive_wallet_clusters(graph)

    assert clusters["summary"]["cluster_count"] == 1
    assert "edge_missing_provenance" in clusters["warnings"]
