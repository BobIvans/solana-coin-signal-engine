from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.cluster_store import (
    append_wallet_graph_event,
    load_wallet_clusters,
    load_wallet_graph,
    persist_wallet_cluster_artifacts,
)
from analytics.wallet_graph_builder import build_wallet_graph, derive_wallet_clusters


PARTICIPANTS = [
    {"wallet": "wallet_a", "funder": "shared", "group_id": ["slot:1"], "launch_id": "launch_1"},
    {"wallet": "wallet_b", "funder": "shared", "group_id": ["slot:1"], "launch_id": "launch_1"},
]


def test_cluster_store_save_and_load_round_trip(tmp_path: Path):
    graph = build_wallet_graph(PARTICIPANTS, metadata={"token_address": "tok-1", "pair_address": "pair-1"})
    clusters = derive_wallet_clusters(graph)

    paths = persist_wallet_cluster_artifacts(
        graph=graph,
        clusters=clusters,
        graph_path=tmp_path / "wallet_graph.json",
        cluster_path=tmp_path / "wallet_clusters.json",
        event_path=tmp_path / "wallet_graph_events.jsonl",
        events=[{"event": "wallet_cluster_store_written", "status": "ok"}],
    )

    loaded_graph = load_wallet_graph(paths["graph_path"])
    loaded_clusters = load_wallet_clusters(paths["cluster_path"])
    assert loaded_graph["summary"]["edge_count"] == 1
    assert loaded_graph["metadata"]["token_address"] == "tok-1"
    assert loaded_clusters["summary"]["cluster_count"] == 1
    assert loaded_clusters["metadata"]["token_address"] == "tok-1"
    assert loaded_clusters["metadata"]["pair_address"] == "pair-1"
    assert paths["event_path"].read_text(encoding="utf-8").strip()


def test_cluster_store_loaders_are_safe_when_artifacts_are_missing(tmp_path: Path):
    assert load_wallet_graph(tmp_path / "missing_graph.json") == {}
    assert load_wallet_clusters(tmp_path / "missing_clusters.json") == {}
    append_wallet_graph_event({"event": "wallet_graph_completed", "status": "ok"}, tmp_path / "events.jsonl")
    assert (tmp_path / "events.jsonl").exists()
