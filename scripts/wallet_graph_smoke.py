from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.cluster_store import append_wallet_graph_event, persist_wallet_cluster_artifacts
from analytics.wallet_graph_builder import build_wallet_graph, derive_wallet_clusters
from utils.io import write_json


FIXTURE = [
    {"wallet": "wallet_a", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_b", "funder": "funder_1", "group_id": ["slot:1"], "launch_id": "launch_alpha"},
    {"wallet": "wallet_c", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_d", "funder": "funder_2", "group_id": ["slot:2"], "launch_id": "launch_beta"},
    {"wallet": "wallet_e", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
    {"wallet": "wallet_f", "funder": "funder_3", "group_id": ["slot:3"], "launch_id": "launch_gamma"},
]


def main() -> int:
    out_dir = ROOT / "data" / "smoke"
    graph = build_wallet_graph(FIXTURE, metadata={"smoke": True, "fixture": "organic_multi_cluster"})
    clusters = derive_wallet_clusters(graph)
    paths = persist_wallet_cluster_artifacts(
        graph=graph,
        clusters=clusters,
        graph_path=out_dir / "wallet_graph.smoke.json",
        cluster_path=out_dir / "wallet_clusters.smoke.json",
    )
    event_path = out_dir / "wallet_graph_events.smoke.jsonl"
    append_wallet_graph_event({"event": "wallet_graph_build_started", "fixture": "organic_multi_cluster", "status": "ok"}, event_path)
    append_wallet_graph_event(
        {"event": "wallet_graph_completed", "fixture": "organic_multi_cluster", "status": "ok", "cluster_count": clusters["summary"]["cluster_count"]},
        event_path,
    )
    status_path = write_json(
        out_dir / "wallet_graph_status.json",
        {
            "status": "ok",
            "graph_nodes": graph["summary"]["node_count"],
            "graph_edges": graph["summary"]["edge_count"],
            "cluster_count": clusters["summary"]["cluster_count"],
            "graph_path": str(paths["graph_path"]),
            "cluster_path": str(paths["cluster_path"]),
            "event_path": str(event_path.resolve()),
        },
    )
    summary = json.loads(status_path.read_text(encoding="utf-8"))
    summary["status_path"] = str(status_path)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
