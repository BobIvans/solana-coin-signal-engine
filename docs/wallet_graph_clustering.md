# Wallet graph clustering

This repository now supports a conservative **graph-backed wallet clustering foundation** layered on top of the original heuristic clustering path.

## What is graph-backed here?

The graph builder in `analytics/wallet_graph_builder.py` turns locally available early-launch evidence into deterministic wallet relationships. Current supported evidence includes:

- shared funders when explicitly present
- co-appearance inside the same bundle/group/slot window
- same-launch linkage
- repeated co-participation across launches
- explicit creator/dev adjacency only when participant evidence marks that relationship

## What is still heuristic?

The existing logic in `analytics/wallet_clustering.py` remains intact and is still used as a safe fallback whenever graph evidence is:

- missing
- too sparse
- only partial
- malformed
- disabled in config

## Artifact outputs

The persistent store in `analytics/cluster_store.py` can write:

- `data/processed/wallet_graph.json`
- `data/processed/wallet_clusters.json`
- `data/processed/wallet_graph_events.jsonl`

The smoke path writes deterministic sample outputs under `data/smoke/`.

## Downstream-safe fields

Existing fields remain available:

- `bundle_wallet_clustering_score`
- `cluster_concentration_ratio`
- `num_unique_clusters_first_60s`
- `creator_in_cluster_flag`

Additive provenance fields now exposed when available:

- `cluster_evidence_status`
- `cluster_evidence_source`
- `cluster_evidence_confidence`
- `cluster_metric_origin`
- `graph_cluster_id_count`
- `graph_cluster_coverage_ratio`
- `creator_cluster_id`
- `dominant_cluster_id`

## Provenance honesty

Canonical emitted `cluster_metric_origin` values are:

- `graph_evidence`
- `heuristic_evidence`
- `missing`

Legacy alias `graph_backed` may be normalized at ingestion boundaries for migration, but fresh emitted `cluster_metric_origin` must use canonical `graph_evidence`.


This PR intentionally does **not** claim complete institutional wallet intelligence. The graph is only as strong as the explicit local evidence that exists in the launch payloads. Weak evidence falls back to heuristics instead of inventing stronger relationships.
