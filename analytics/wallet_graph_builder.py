"""Deterministic wallet graph construction for early-launch clustering."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

GRAPH_CONTRACT_VERSION = "wallet_graph.v1"
CLUSTER_CONTRACT_VERSION = "wallet_clusters.v1"

_FUNDING_KEYS = (
    "funder",
    "funding_source",
    "funding_wallet",
    "source_wallet",
    "source_owner",
    "funded_by",
    "shared_funder",
)
_GROUP_KEYS = (
    "group_key",
    "group_id",
    "bundle_id",
    "cohort_id",
    "window_id",
    "slot_group",
    "slot",
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
_CREATOR_WALLET_KEYS = (
    "creator_wallet",
    "deployer_wallet",
    "mint_authority",
    "update_authority",
    "dev_wallet",
    "dev_wallet_est",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _normalize_timestamp(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        return ts if ts > 0 else None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        ts = int(text)
        return ts if ts > 0 else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    ts = int(parsed.timestamp())
    return ts if ts > 0 else None


def _safe_label(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _cluster_id_from_wallets(wallets: list[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(wallets)).encode("utf-8")).hexdigest()[:12]
    anchor = sorted(wallets)[0][:8]
    return f"cluster_{anchor}_{digest}"


def _cluster_confidence(edge_weights: list[float], evidence_types: set[str], coverage_ratio: float) -> float:
    if not edge_weights:
        return 0.0
    avg_weight = sum(edge_weights) / len(edge_weights)
    evidence_bonus = min(0.2, 0.04 * max(0, len(evidence_types) - 1))
    coverage_bonus = min(0.15, max(0.0, coverage_ratio) * 0.15)
    return round(min(0.95, avg_weight + evidence_bonus + coverage_bonus), 6)


def derive_graph_edges(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
) -> dict[str, Any]:
    """Derive deterministic graph edges and node evidence from participants."""

    normalized: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    invalid_timestamps = 0
    creator = _as_wallet(creator_wallet)

    for index, participant in enumerate(participants or []):
        if not isinstance(participant, dict):
            warnings.append(f"participant_{index}_not_dict")
            continue
        wallet = _participant_wallet(participant)
        if not wallet:
            warnings.append(f"participant_{index}_missing_wallet")
            continue

        bucket = normalized.setdefault(
            wallet,
            {
                "wallet": wallet,
                "funders": set(),
                "groups": set(),
                "launches": set(),
                "timestamps": set(),
                "creator_linked": False,
                "creator_refs": set(),
            },
        )
        for key in _FUNDING_KEYS:
            for item in _iter_values(participant.get(key)):
                value = _as_wallet(item)
                if value:
                    bucket["funders"].add(value)
        for key in _GROUP_KEYS:
            for item in _iter_values(participant.get(key)):
                value = _safe_label(item)
                if value:
                    bucket["groups"].add(value)
        for key in _LAUNCH_KEYS:
            for item in _iter_values(participant.get(key)):
                value = _safe_label(item)
                if value:
                    bucket["launches"].add(value)
        for key in ("timestamp", "blockTime", "time", "slot_time", "seen_at"):
            ts = _normalize_timestamp(participant.get(key))
            if ts is not None:
                bucket["timestamps"].add(ts)
                break
            if participant.get(key) not in (None, ""):
                invalid_timestamps += 1
                break
        if any(_as_bool(participant.get(key)) for key in _CREATOR_LINK_KEYS):
            bucket["creator_linked"] = True
        for key in _CREATOR_WALLET_KEYS:
            value = _as_wallet(participant.get(key))
            if value:
                bucket["creator_refs"].add(value)

    if invalid_timestamps:
        warnings.append(f"invalid_timestamps:{invalid_timestamps}")

    if creator and creator in normalized:
        normalized[creator]["creator_linked"] = True
        normalized[creator]["creator_refs"].add(creator)

    pair_provenance: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def add_pair(left: str, right: str, evidence_type: str, weight: float, **details: Any) -> None:
        if left == right:
            return
        pair = tuple(sorted((left, right)))
        provenance = {
            "evidence_type": evidence_type,
            "weight": round(float(weight), 6),
            **{key: value for key, value in details.items() if value not in (None, "", [], {})},
        }
        pair_provenance[pair].append(provenance)

    funder_to_wallets: dict[str, set[str]] = defaultdict(set)
    group_to_wallets: dict[str, set[str]] = defaultdict(set)
    launch_to_wallets: dict[str, set[str]] = defaultdict(set)

    for wallet, evidence in normalized.items():
        for funder in evidence["funders"]:
            funder_to_wallets[funder].add(wallet)
        for group in evidence["groups"]:
            group_to_wallets[group].add(wallet)
        for launch in evidence["launches"]:
            launch_to_wallets[launch].add(wallet)

    for funder, wallets in sorted(funder_to_wallets.items()):
        ordered = sorted(wallets)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                add_pair(left, right, "shared_funder", 0.85, funder=funder)

    for group, wallets in sorted(group_to_wallets.items()):
        ordered = sorted(wallets)
        if len(ordered) < 2:
            continue
        weight = min(0.8, 0.45 + 0.05 * max(0, len(ordered) - 2))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                add_pair(left, right, "co_bundle_window", weight, group=group)

    for launch, wallets in sorted(launch_to_wallets.items()):
        ordered = sorted(wallets)
        if len(ordered) < 2:
            continue
        weight = min(0.75, 0.4 + 0.05 * max(0, len(ordered) - 2))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                add_pair(left, right, "same_launch", weight, launch=launch)

    wallet_launch_sets = {wallet: frozenset(evidence["launches"]) for wallet, evidence in normalized.items() if evidence["launches"]}
    ordered_wallets = sorted(wallet_launch_sets)
    for index, left in enumerate(ordered_wallets):
        for right in ordered_wallets[index + 1 :]:
            overlap = sorted(wallet_launch_sets[left].intersection(wallet_launch_sets[right]))
            if len(overlap) >= 2:
                weight = min(0.9, 0.55 + 0.05 * (len(overlap) - 2))
                add_pair(left, right, "repeated_launch_coparticipation", weight, launches=overlap)

    if creator:
        for wallet, evidence in sorted(normalized.items()):
            if wallet == creator:
                continue
            explicit_ref = creator in evidence["creator_refs"]
            if explicit_ref or evidence["creator_linked"]:
                add_pair(creator, wallet, "creator_adjacency", 0.75 if explicit_ref else 0.65, creator_wallet=creator)

    edges: list[dict[str, Any]] = []
    for (left, right), provenance in sorted(pair_provenance.items()):
        total_weight = round(sum(float(item["weight"]) for item in provenance) / len(provenance), 6)
        evidence_types = sorted({str(item["evidence_type"]) for item in provenance})
        edges.append(
            {
                "source": left,
                "target": right,
                "weight": total_weight,
                "evidence_count": len(provenance),
                "evidence_types": evidence_types,
                "provenance": provenance,
            }
        )

    nodes = [
        {
            "wallet": wallet,
            "creator_linked": bool(evidence["creator_linked"]),
            "funders": sorted(evidence["funders"]),
            "groups": sorted(evidence["groups"]),
            "launches": sorted(evidence["launches"]),
            "timestamps": sorted(evidence["timestamps"]),
        }
        for wallet, evidence in sorted(normalized.items())
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "warnings": sorted(set(warnings)),
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "warning_count": len(sorted(set(warnings))),
        },
    }


def normalize_wallet_graph(
    graph: dict[str, Any] | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize graph payloads into a deterministic artifact shape."""

    raw = graph or {}
    nodes = []
    wallets_seen: set[str] = set()
    warnings: set[str] = set(item for item in raw.get("warnings", []) if isinstance(item, str))

    for node in raw.get("nodes", []) if isinstance(raw.get("nodes"), list) else []:
        if not isinstance(node, dict):
            warnings.add("node_not_dict")
            continue
        wallet = _as_wallet(node.get("wallet"))
        if not wallet:
            warnings.add("node_missing_wallet")
            continue
        if wallet in wallets_seen:
            continue
        wallets_seen.add(wallet)
        nodes.append(
            {
                "wallet": wallet,
                "creator_linked": bool(node.get("creator_linked")),
                "funders": sorted({_as_wallet(item) for item in node.get("funders", []) if _as_wallet(item)}),
                "groups": sorted({_safe_label(item) for item in node.get("groups", []) if _safe_label(item)}),
                "launches": sorted({_safe_label(item) for item in node.get("launches", []) if _safe_label(item)}),
                "timestamps": sorted({int(item) for item in node.get("timestamps", []) if isinstance(item, int) and item > 0}),
            }
        )

    edges = []
    edge_pairs: set[tuple[str, str, tuple[str, ...]]] = set()
    for edge in raw.get("edges", []) if isinstance(raw.get("edges"), list) else []:
        if not isinstance(edge, dict):
            warnings.add("edge_not_dict")
            continue
        provenance = edge.get("provenance") if isinstance(edge.get("provenance"), list) else []
        if not provenance:
            warnings.add("edge_missing_provenance")
        left = _as_wallet(edge.get("source"))
        right = _as_wallet(edge.get("target"))
        if not left or not right or left == right:
            warnings.add("edge_invalid_wallets")
            continue
        if not provenance:
            continue
        evidence_types = sorted({str(item.get("evidence_type")) for item in provenance if isinstance(item, dict) and item.get("evidence_type")})
        if not evidence_types:
            warnings.add("edge_missing_evidence_type")
            continue
        pair = tuple(sorted((left, right)))
        dedupe_key = (pair[0], pair[1], tuple(evidence_types))
        if dedupe_key in edge_pairs:
            continue
        edge_pairs.add(dedupe_key)
        weight = edge.get("weight")
        try:
            normalized_weight = round(float(weight), 6)
        except (TypeError, ValueError):
            normalized_weight = round(sum(float(item.get("weight") or 0.0) for item in provenance if isinstance(item, dict)) / max(1, len(provenance)), 6)
        if normalized_weight <= 0:
            warnings.add("edge_non_positive_weight")
            continue
        edges.append(
            {
                "source": pair[0],
                "target": pair[1],
                "weight": normalized_weight,
                "evidence_count": int(edge.get("evidence_count") or len(provenance)),
                "evidence_types": evidence_types,
                "provenance": provenance,
            }
        )

    nodes.sort(key=lambda item: item["wallet"])
    edges.sort(key=lambda item: (item["source"], item["target"], ",".join(item["evidence_types"])))
    density = 0.0
    if len(nodes) > 1:
        density = round((2.0 * len(edges)) / (len(nodes) * (len(nodes) - 1)), 6)

    artifact_metadata = {
        "generated_at": _utc_now_iso(),
        "contract_version": GRAPH_CONTRACT_VERSION,
        **{key: value for key, value in (metadata or {}).items() if value not in (None, "", [], {})},
    }
    return {
        "metadata": artifact_metadata,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "warning_count": len(warnings),
            "density": density,
            "evidence_types": sorted({evidence for edge in edges for evidence in edge["evidence_types"]}),
        },
        "warnings": sorted(warnings),
    }


def build_wallet_graph(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic wallet relationship graph from local participant evidence."""

    derived = derive_graph_edges(participants, creator_wallet=creator_wallet)
    return normalize_wallet_graph(derived, metadata=metadata)


def derive_wallet_clusters(
    graph: dict[str, Any] | None,
    *,
    min_weight: float = 0.5,
) -> dict[str, Any]:
    """Derive deterministic connected-component clusters from a wallet graph."""

    normalized = normalize_wallet_graph(graph)
    nodes = [node["wallet"] for node in normalized["nodes"]]
    parent = {wallet: wallet for wallet in nodes}

    def find(item: str) -> str:
        root = parent[item]
        if root != item:
            parent[item] = find(root)
        return parent[item]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    eligible_edges = []
    for edge in normalized["edges"]:
        if float(edge.get("weight") or 0.0) < float(min_weight):
            continue
        left = edge["source"]
        right = edge["target"]
        if left not in parent or right not in parent:
            continue
        eligible_edges.append(edge)
        union(left, right)

    components: dict[str, list[str]] = defaultdict(list)
    for wallet in nodes:
        components[find(wallet)].append(wallet)

    edges_by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in eligible_edges:
        root = find(edge["source"])
        if root == find(edge["target"]):
            edges_by_component[root].append(edge)

    wallet_to_cluster: dict[str, str] = {}
    clusters: list[dict[str, Any]] = []
    creator_linked_wallets = {node["wallet"] for node in normalized["nodes"] if node.get("creator_linked")}

    for root, wallets in sorted(components.items()):
        ordered_wallets = sorted(wallets)
        if len(ordered_wallets) < 2:
            continue
        component_edges = edges_by_component.get(root, [])
        if not component_edges:
            continue
        cluster_id = _cluster_id_from_wallets(ordered_wallets)
        for wallet in ordered_wallets:
            wallet_to_cluster[wallet] = cluster_id
        evidence_types = sorted({item for edge in component_edges for item in edge.get("evidence_types", [])})
        funding_sources_seen = sorted({prov.get("funder") for edge in component_edges for prov in edge.get("provenance", []) if isinstance(prov, dict) and prov.get("funder")})
        launches_seen = sorted({launch for edge in component_edges for prov in edge.get("provenance", []) if isinstance(prov, dict) for launch in _iter_values(prov.get("launch") or prov.get("launches")) if _safe_label(launch)})
        coverage_ratio = len(ordered_wallets) / max(1, len(nodes))
        confidence = _cluster_confidence([float(edge.get("weight") or 0.0) for edge in component_edges], set(evidence_types), coverage_ratio)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "wallets": ordered_wallets,
                "wallet_count": len(ordered_wallets),
                "edge_count": len(component_edges),
                "evidence_types": evidence_types,
                "funding_sources_seen": funding_sources_seen,
                "launches_seen": launches_seen,
                "creator_linked_flag": any(wallet in creator_linked_wallets for wallet in ordered_wallets),
                "derived_from": "graph_evidence",
                "cluster_confidence": confidence,
            }
        )

    clusters.sort(key=lambda item: item["cluster_id"])
    mapped_cluster_ids = sorted({cluster_id for cluster_id in wallet_to_cluster.values()})
    return {
        "metadata": {
            "generated_at": normalized["metadata"]["generated_at"],
            "contract_version": CLUSTER_CONTRACT_VERSION,
            "derivation_mode": "graph_connected_components",
            "source_contract_version": normalized["metadata"].get("contract_version", GRAPH_CONTRACT_VERSION),
        },
        "clusters": clusters,
        "wallet_to_cluster": {wallet: wallet_to_cluster[wallet] for wallet in sorted(wallet_to_cluster)},
        "summary": {
            "cluster_count": len(clusters),
            "wallet_coverage_count": len(wallet_to_cluster),
            "node_count": len(nodes),
            "edge_count": len(eligible_edges),
            "cluster_ids": mapped_cluster_ids,
        },
        "warnings": list(normalized.get("warnings", [])),
    }
