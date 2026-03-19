"""Deterministic, explainable wallet clustering heuristics for early launch activity."""

from __future__ import annotations

from collections import defaultdict
from math import ceil
from typing import Any

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


def compute_wallet_clustering_metrics(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    participant_wallets: list[str] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper returning all wallet clustering contract fields."""

    cluster_keys = infer_wallet_cluster_keys(participants, creator_wallet=creator_wallet)
    cluster_ids = assign_wallet_cluster_ids(cluster_keys)
    wallets = participant_wallets or [wallet for wallet in (_participant_wallet(item) for item in participants) if wallet]
    concentration_ratio = compute_cluster_concentration_ratio(cluster_ids, wallets)
    unique_clusters = compute_num_unique_clusters_first_60s(cluster_ids, wallets)
    creator_flag = detect_creator_in_cluster(cluster_ids, wallets, creator_wallet)
    clustering_score = compute_bundle_wallet_clustering_score(
        cluster_concentration_ratio=concentration_ratio,
        num_unique_clusters_first_60s=unique_clusters,
        creator_in_cluster_flag=creator_flag,
    )
    return {
        "bundle_wallet_clustering_score": clustering_score,
        "cluster_concentration_ratio": concentration_ratio,
        "num_unique_clusters_first_60s": unique_clusters,
        "creator_in_cluster_flag": creator_flag,
    }
