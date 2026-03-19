"""Deterministic, explainable wallet clustering heuristics with graph-backed fallback safety."""

from __future__ import annotations

from collections import defaultdict
from math import ceil
from typing import Any

from analytics.cluster_store import persist_wallet_cluster_artifacts
from analytics.wallet_graph_builder import build_wallet_graph, derive_wallet_clusters
from utils.logger import log_info, log_warning

_CLUSTER_SCORE_MAX_UNIQUE = 5
_FUNDING_KEYS = (
    "funder",
    "funding_source",
    "funding_wallet",
    "source_wallet",
    "source_owner",
    "funded_by",
    "shared_funder",
)
_LAUNCH_KEYS = (
    "launch_id",
    "launch_group",
    "launch_key",
    "launch_cluster",
    "same_launch_tag",
)
_CREATOR_LINK_KEYS = (
    "creator_linked",
    "creator_overlap",
    "creator_related",
    "dev_linked",
)


def _as_wallet(value: Any) -> str | None:
    if value is None:
        return None
    wallet = str(value).strip()
    return wallet or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _participant_wallet(participant: dict[str, Any]) -> str | None:
    for key in ("wallet", "wallet_address", "address", "owner", "signer", "fee_payer", "actor"):
        wallet = _as_wallet(participant.get(key))
        if wallet:
            return wallet
    return None


def _evidence_coverage_threshold(total_wallets: int) -> int:
    return max(2, min(total_wallets, ceil(total_wallets * 0.5)))


def infer_wallet_cluster_keys(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
) -> dict[str, list[str]]:
    """Infer deterministic cluster keys from shallow, explainable evidence."""

    normalized: dict[str, dict[str, set[str] | bool]] = {}
    creator = _as_wallet(creator_wallet)

    for participant in participants:
        if not isinstance(participant, dict):
            continue
        wallet = _participant_wallet(participant)
        if not wallet:
            continue
        bucket = normalized.setdefault(
            wallet,
            {
                "funders": set(),
                "groups": set(),
                "launches": set(),
                "creator_linked": False,
            },
        )
        for key in _FUNDING_KEYS:
            for item in _iter_values(participant.get(key)):
                value = _as_wallet(item)
                if value:
                    bucket["funders"].add(value)
        for key in ("group_key", "group_id", "bundle_id", "cohort_id", "window_id", "slot_group"):
            for item in _iter_values(participant.get(key)):
                value = str(item).strip()
                if value:
                    bucket["groups"].add(value)
        for key in _LAUNCH_KEYS:
            for item in _iter_values(participant.get(key)):
                value = str(item).strip()
                if value:
                    bucket["launches"].add(value)
        if any(_as_bool(participant.get(key)) for key in _CREATOR_LINK_KEYS):
            bucket["creator_linked"] = True

    if creator and creator in normalized:
        normalized[creator]["creator_linked"] = True

    group_counts: dict[tuple[str, str], int] = defaultdict(int)
    group_to_wallets: dict[str, list[str]] = defaultdict(list)
    launch_to_wallets: dict[str, list[str]] = defaultdict(list)

    for wallet, evidence in normalized.items():
        for group_id in sorted(evidence["groups"]):
            group_to_wallets[group_id].append(wallet)
        for launch_id in sorted(evidence["launches"]):
            launch_to_wallets[launch_id].append(wallet)

    for wallets in group_to_wallets.values():
        unique_wallets = sorted(set(wallets))
        for idx, left in enumerate(unique_wallets):
            for right in unique_wallets[idx + 1 :]:
                group_counts[(left, right)] += 1

    cluster_keys: dict[str, set[str]] = {wallet: set() for wallet in normalized}
    for wallet, evidence in normalized.items():
        for funder in sorted(evidence["funders"]):
            cluster_keys[wallet].add(f"funder:{funder}")
        if creator and evidence["creator_linked"]:
            cluster_keys[wallet].add(f"creator:{creator}")

    for (left, right), count in sorted(group_counts.items()):
        if count >= 2:
            key = f"coappear:{left}|{right}"
            cluster_keys[left].add(key)
            cluster_keys[right].add(key)

    for launch_id, wallets in sorted(launch_to_wallets.items()):
        unique_wallets = sorted(set(wallets))
        if len(unique_wallets) < 2:
            continue
        key = f"launch:{launch_id}"
        for wallet in unique_wallets:
            cluster_keys[wallet].add(key)

    return {wallet: sorted(keys) for wallet, keys in sorted(cluster_keys.items()) if keys}


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self.parent[right_root] = left_root
        else:
            self.parent[left_root] = right_root


def assign_wallet_cluster_ids(cluster_keys_by_wallet: dict[str, list[str]]) -> dict[str, str]:
    """Assign stable cluster ids to wallets that share inferred cluster keys."""

    if not cluster_keys_by_wallet:
        return {}

    union_find = _UnionFind(sorted(cluster_keys_by_wallet))
    wallets_by_key: dict[str, list[str]] = defaultdict(list)
    for wallet, keys in sorted(cluster_keys_by_wallet.items()):
        for key in keys:
            wallets_by_key[key].append(wallet)

    for wallets in wallets_by_key.values():
        if len(wallets) < 2:
            continue
        anchor = wallets[0]
        for wallet in wallets[1:]:
            union_find.union(anchor, wallet)

    root_to_wallets: dict[str, list[str]] = defaultdict(list)
    for wallet in sorted(cluster_keys_by_wallet):
        root_to_wallets[union_find.find(wallet)].append(wallet)

    cluster_id_map: dict[str, str] = {}
    for index, root in enumerate(sorted(root_to_wallets), start=1):
        wallets = sorted(root_to_wallets[root])
        if len(wallets) < 2:
            continue
        cluster_id = f"cluster_{index}"
        for wallet in wallets:
            cluster_id_map[wallet] = cluster_id
    return cluster_id_map


def compute_cluster_concentration_ratio(
    cluster_ids_by_wallet: dict[str, str],
    participant_wallets: list[str],
) -> float | None:
    """Dominant inferred cluster share across first-window participants."""

    normalized_wallets = sorted({_as_wallet(wallet) for wallet in participant_wallets if _as_wallet(wallet)})
    if len(normalized_wallets) < 2:
        return None

    cluster_counts: dict[str, int] = defaultdict(int)
    for wallet in normalized_wallets:
        cluster_id = cluster_ids_by_wallet.get(wallet)
        if cluster_id:
            cluster_counts[cluster_id] += 1

    if not cluster_counts:
        return None

    covered_wallets = sum(cluster_counts.values())
    if covered_wallets < _evidence_coverage_threshold(len(normalized_wallets)):
        return None

    dominant_cluster_size = max(cluster_counts.values())
    return round(dominant_cluster_size / len(normalized_wallets), 6)


def compute_num_unique_clusters_first_60s(
    cluster_ids_by_wallet: dict[str, str],
    participant_wallets: list[str],
) -> int | None:
    """Count distinct inferred clusters among first-window participants."""

    normalized_wallets = {_as_wallet(wallet) for wallet in participant_wallets if _as_wallet(wallet)}
    if len(normalized_wallets) < 2:
        return None

    clusters = {cluster_ids_by_wallet[wallet] for wallet in normalized_wallets if wallet in cluster_ids_by_wallet}
    if not clusters:
        return None
    covered_wallets = sum(1 for wallet in normalized_wallets if wallet in cluster_ids_by_wallet)
    if covered_wallets < _evidence_coverage_threshold(len(normalized_wallets)):
        return None
    return len(clusters)


def detect_creator_in_cluster(
    cluster_ids_by_wallet: dict[str, str],
    participant_wallets: list[str],
    creator_wallet: str | None,
) -> bool | None:
    """Return whether the creator shares an inferred cluster with early buyers."""

    creator = _as_wallet(creator_wallet)
    if not creator:
        return None
    creator_cluster = cluster_ids_by_wallet.get(creator)
    if not creator_cluster:
        return None

    normalized_wallets = {_as_wallet(wallet) for wallet in participant_wallets if _as_wallet(wallet)}
    if not normalized_wallets:
        return None
    for wallet in normalized_wallets:
        if wallet == creator:
            continue
        if cluster_ids_by_wallet.get(wallet) == creator_cluster:
            return True
    return False


def compute_bundle_wallet_clustering_score(
    *,
    cluster_concentration_ratio: float | None,
    num_unique_clusters_first_60s: int | None,
    creator_in_cluster_flag: bool | None,
) -> float | None:
    """Compute a conservative, explainable suspiciousness score in [0, 1]."""

    if cluster_concentration_ratio is None or num_unique_clusters_first_60s is None:
        return None

    concentration = max(0.0, min(1.0, float(cluster_concentration_ratio)))
    unique_clusters = max(1, int(num_unique_clusters_first_60s))
    diversity_penalty = 1.0 / min(unique_clusters, _CLUSTER_SCORE_MAX_UNIQUE)
    creator_penalty = 0.1 if creator_in_cluster_flag is True else 0.0
    score = 0.7 * concentration + 0.2 * diversity_penalty + creator_penalty
    return round(max(0.0, min(1.0, score)), 6)


def _metric_defaults() -> dict[str, Any]:
    return {
        "bundle_wallet_clustering_score": None,
        "cluster_concentration_ratio": None,
        "num_unique_clusters_first_60s": None,
        "creator_in_cluster_flag": None,
        "cluster_evidence_status": "missing",
        "cluster_evidence_source": "missing",
        "cluster_evidence_confidence": None,
        "cluster_metric_origin": "missing",
        "graph_cluster_id_count": 0,
        "graph_cluster_coverage_ratio": 0.0,
        "creator_cluster_id": None,
        "dominant_cluster_id": None,
    }


def _graph_coverage_is_meaningful(mapped_wallets: dict[str, str], participant_wallets: list[str]) -> bool:
    if not participant_wallets:
        return False
    normalized = sorted({_as_wallet(wallet) for wallet in participant_wallets if _as_wallet(wallet)})
    if len(normalized) < 2:
        return False
    covered = sum(1 for wallet in normalized if wallet in mapped_wallets)
    return covered >= _evidence_coverage_threshold(len(normalized)) and (covered / len(normalized)) > 0.5


def _dominant_cluster_id(cluster_ids_by_wallet: dict[str, str], wallets: list[str]) -> str | None:
    counts: dict[str, int] = defaultdict(int)
    for wallet in wallets:
        cluster_id = cluster_ids_by_wallet.get(wallet)
        if cluster_id:
            counts[cluster_id] += 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def resolve_wallet_cluster_assignments(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    participant_wallets: list[str] | None = None,
    settings: Any | None = None,
    graph_artifact: dict[str, Any] | None = None,
    clusters_artifact: dict[str, Any] | None = None,
    persist_artifacts: bool = False,
    artifact_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve wallet cluster assignments using graph evidence first, heuristic fallback second."""

    wallets = sorted({_as_wallet(wallet) for wallet in (participant_wallets or []) if _as_wallet(wallet)})
    if not wallets:
        wallets = sorted({_participant_wallet(item) for item in participants if _participant_wallet(item)})

    defaults = {
        "cluster_ids_by_wallet": {},
        "graph": graph_artifact or {},
        "clusters": clusters_artifact or {},
        "evidence_status": "missing",
        "evidence_source": "missing",
        "metric_origin": "missing",
        "evidence_confidence": None,
        "coverage_ratio": 0.0,
        "graph_cluster_id_count": 0,
        "creator_cluster_id": None,
        "dominant_cluster_id": None,
        "warnings": [],
    }
    if len(wallets) < 2:
        return defaults

    graph_enabled = True if settings is None else bool(getattr(settings, "WALLET_GRAPH_ENABLED", True))
    existing_clusters = clusters_artifact or {}
    wallet_to_cluster = existing_clusters.get("wallet_to_cluster") if isinstance(existing_clusters, dict) else {}
    if isinstance(wallet_to_cluster, dict):
        mapped = {wallet: str(cluster_id) for wallet, cluster_id in wallet_to_cluster.items() if _as_wallet(wallet)}
        if _graph_coverage_is_meaningful(mapped, wallets):
            confidence_values = []
            summaries = {item.get("cluster_id"): item for item in existing_clusters.get("clusters", []) if isinstance(item, dict)}
            for cluster_id in set(mapped.values()):
                summary = summaries.get(cluster_id) or {}
                try:
                    confidence_values.append(float(summary.get("cluster_confidence") or 0.0))
                except (TypeError, ValueError):
                    continue
            confidence = round(sum(confidence_values) / len(confidence_values), 6) if confidence_values else None
            return {
                "cluster_ids_by_wallet": mapped,
                "graph": graph_artifact or {},
                "clusters": existing_clusters,
                "evidence_status": "graph_backed",
                "evidence_source": "persistent_artifact",
                "metric_origin": "graph_evidence",
                "evidence_confidence": confidence,
                "coverage_ratio": round(sum(1 for wallet in wallets if wallet in mapped) / len(wallets), 6),
                "graph_cluster_id_count": len(set(mapped.values())),
                "creator_cluster_id": mapped.get(_as_wallet(creator_wallet) or ""),
                "dominant_cluster_id": _dominant_cluster_id(mapped, wallets),
                "warnings": list(existing_clusters.get("warnings", [])),
            }

    if graph_enabled:
        scope = {key: value for key, value in (artifact_scope or {}).items() if value not in (None, "", [], {})}
        graph = build_wallet_graph(participants, creator_wallet=creator_wallet, metadata=scope)
        clusters = derive_wallet_clusters(graph, min_weight=float(getattr(settings, "WALLET_GRAPH_EDGE_MIN_WEIGHT", 0.5) or 0.5))
        graph_wallet_map = clusters.get("wallet_to_cluster") if isinstance(clusters, dict) else {}
        if isinstance(graph_wallet_map, dict):
            mapped = {wallet: str(cluster_id) for wallet, cluster_id in graph_wallet_map.items() if _as_wallet(wallet)}
            if _graph_coverage_is_meaningful(mapped, wallets):
                cluster_summaries = {item.get("cluster_id"): item for item in clusters.get("clusters", []) if isinstance(item, dict)}
                cluster_confidences = []
                for cluster_id in set(mapped.values()):
                    summary = cluster_summaries.get(cluster_id) or {}
                    try:
                        cluster_confidences.append(float(summary.get("cluster_confidence") or 0.0))
                    except (TypeError, ValueError):
                        continue
                confidence = round(sum(cluster_confidences) / len(cluster_confidences), 6) if cluster_confidences else None
                if persist_artifacts and settings is not None:
                    events = [
                        {"event": "wallet_graph_build_started", **scope},
                        {"event": "wallet_graph_edges_derived", "node_count": graph.get("summary", {}).get("node_count", 0), "edge_count": graph.get("summary", {}).get("edge_count", 0), **scope},
                        {"event": "wallet_graph_normalized", "status": "ok", **scope},
                        {"event": "wallet_clusters_derived", "cluster_count": clusters.get("summary", {}).get("cluster_count", 0), "status": "ok", **scope},
                        {"event": "wallet_cluster_store_written", "status": "ok", **scope},
                        {"event": "wallet_graph_completed", "status": "ok", **scope},
                    ]
                    persist_wallet_cluster_artifacts(graph=graph, clusters=clusters, settings=settings, events=events)
                log_info(
                    "wallet_graph_completed",
                    status="ok",
                    node_count=graph.get("summary", {}).get("node_count", 0),
                    edge_count=graph.get("summary", {}).get("edge_count", 0),
                    cluster_count=clusters.get("summary", {}).get("cluster_count", 0),
                    provenance_mode="graph_evidence",
                    **scope,
                )
                return {
                    "cluster_ids_by_wallet": mapped,
                    "graph": graph,
                    "clusters": clusters,
                    "evidence_status": "graph_backed",
                    "evidence_source": "inline_graph_builder",
                    "metric_origin": "graph_evidence",
                    "evidence_confidence": confidence,
                    "coverage_ratio": round(sum(1 for wallet in wallets if wallet in mapped) / len(wallets), 6),
                    "graph_cluster_id_count": len(set(mapped.values())),
                    "creator_cluster_id": mapped.get(_as_wallet(creator_wallet) or ""),
                    "dominant_cluster_id": _dominant_cluster_id(mapped, wallets),
                    "warnings": list(graph.get("warnings", [])) + list(clusters.get("warnings", [])),
                }
            reason = "insufficient_graph_coverage"
            log_warning(
                "wallet_graph_partial",
                status=reason,
                node_count=graph.get("summary", {}).get("node_count", 0),
                edge_count=graph.get("summary", {}).get("edge_count", 0),
                cluster_count=clusters.get("summary", {}).get("cluster_count", 0),
                provenance_mode="graph_partial",
                **scope,
            )

    cluster_keys = infer_wallet_cluster_keys(participants, creator_wallet=creator_wallet)
    heuristic_cluster_ids = assign_wallet_cluster_ids(cluster_keys)
    if heuristic_cluster_ids:
        log_info(
            "wallet_graph_fallback_heuristic",
            reason="graph_missing_or_insufficient",
            wallet_count=len(wallets),
            clustered_wallet_count=len(heuristic_cluster_ids),
            provenance_mode="heuristic_fallback",
            **{key: value for key, value in (artifact_scope or {}).items() if value not in (None, "", [], {})},
        )
        return {
            "cluster_ids_by_wallet": heuristic_cluster_ids,
            "graph": {},
            "clusters": {},
            "evidence_status": "heuristic_fallback",
            "evidence_source": "heuristic_keys",
            "metric_origin": "heuristic_fallback",
            "evidence_confidence": 0.35,
            "coverage_ratio": round(len(heuristic_cluster_ids) / len(wallets), 6),
            "graph_cluster_id_count": 0,
            "creator_cluster_id": heuristic_cluster_ids.get(_as_wallet(creator_wallet) or ""),
            "dominant_cluster_id": _dominant_cluster_id(heuristic_cluster_ids, wallets),
            "warnings": [],
        }

    return defaults


def compute_wallet_clustering_metrics(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    participant_wallets: list[str] | None = None,
    settings: Any | None = None,
    graph_artifact: dict[str, Any] | None = None,
    clusters_artifact: dict[str, Any] | None = None,
    persist_artifacts: bool = False,
    artifact_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper returning bundle cluster fields plus provenance metadata."""

    out = _metric_defaults()
    wallets = participant_wallets or [wallet for wallet in (_participant_wallet(item) for item in participants) if wallet]
    resolved = resolve_wallet_cluster_assignments(
        participants,
        creator_wallet=creator_wallet,
        participant_wallets=wallets,
        settings=settings,
        graph_artifact=graph_artifact,
        clusters_artifact=clusters_artifact,
        persist_artifacts=persist_artifacts,
        artifact_scope=artifact_scope,
    )
    cluster_ids = resolved["cluster_ids_by_wallet"]
    concentration_ratio = compute_cluster_concentration_ratio(cluster_ids, wallets)
    unique_clusters = compute_num_unique_clusters_first_60s(cluster_ids, wallets)
    creator_flag = detect_creator_in_cluster(cluster_ids, wallets, creator_wallet)
    clustering_score = compute_bundle_wallet_clustering_score(
        cluster_concentration_ratio=concentration_ratio,
        num_unique_clusters_first_60s=unique_clusters,
        creator_in_cluster_flag=creator_flag,
    )
    out.update(
        {
            "bundle_wallet_clustering_score": clustering_score,
            "cluster_concentration_ratio": concentration_ratio,
            "num_unique_clusters_first_60s": unique_clusters,
            "creator_in_cluster_flag": creator_flag,
            "cluster_evidence_status": resolved["evidence_status"],
            "cluster_evidence_source": resolved["evidence_source"],
            "cluster_evidence_confidence": resolved["evidence_confidence"],
            "cluster_metric_origin": resolved["metric_origin"],
            "graph_cluster_id_count": resolved["graph_cluster_id_count"],
            "graph_cluster_coverage_ratio": resolved["coverage_ratio"],
            "creator_cluster_id": resolved["creator_cluster_id"],
            "dominant_cluster_id": resolved["dominant_cluster_id"],
        }
    )
    return out
