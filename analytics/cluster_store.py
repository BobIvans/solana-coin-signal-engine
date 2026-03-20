"""Persistent store helpers for wallet graph and cluster artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from analytics.wallet_graph_builder import build_wallet_graph, derive_wallet_clusters
from utils.io import append_jsonl, read_json, write_json

_DEFAULT_GRAPH_FILENAME = "wallet_graph.json"
_DEFAULT_CLUSTER_FILENAME = "wallet_clusters.json"
_DEFAULT_EVENT_FILENAME = "wallet_graph_events.jsonl"


def _metadata_scope_values(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in (metadata or {}).items() if value not in (None, "", [], {})}


def _path_or_default(path: Path | str | None, default: Path) -> Path:
    return Path(path).expanduser().resolve() if path is not None else default.expanduser().resolve()


def wallet_graph_output_path(settings: Any | None = None, override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    if settings is not None and getattr(settings, "WALLET_GRAPH_OUTPUT_PATH", None):
        return Path(settings.WALLET_GRAPH_OUTPUT_PATH).expanduser().resolve()
    base = Path(getattr(settings, "PROCESSED_DATA_DIR", "./data/processed"))
    return (base / _DEFAULT_GRAPH_FILENAME).expanduser().resolve()


def wallet_cluster_output_path(settings: Any | None = None, override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    if settings is not None and getattr(settings, "WALLET_CLUSTER_OUTPUT_PATH", None):
        return Path(settings.WALLET_CLUSTER_OUTPUT_PATH).expanduser().resolve()
    base = Path(getattr(settings, "PROCESSED_DATA_DIR", "./data/processed"))
    return (base / _DEFAULT_CLUSTER_FILENAME).expanduser().resolve()


def wallet_graph_events_path(settings: Any | None = None, override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    if settings is not None and getattr(settings, "WALLET_GRAPH_EVENTS_PATH", None):
        return Path(settings.WALLET_GRAPH_EVENTS_PATH).expanduser().resolve()
    base = Path(getattr(settings, "PROCESSED_DATA_DIR", "./data/processed"))
    return (base / _DEFAULT_EVENT_FILENAME).expanduser().resolve()


def load_wallet_graph(path: Path | str | None = None, *, settings: Any | None = None) -> dict[str, Any]:
    target = _path_or_default(path, wallet_graph_output_path(settings=settings))
    return read_json(target, default={}) or {}


def load_wallet_clusters(path: Path | str | None = None, *, settings: Any | None = None) -> dict[str, Any]:
    target = _path_or_default(path, wallet_cluster_output_path(settings=settings))
    return read_json(target, default={}) or {}


def save_wallet_graph(graph: dict[str, Any], path: Path | str | None = None, *, settings: Any | None = None) -> Path:
    target = _path_or_default(path, wallet_graph_output_path(settings=settings))
    return write_json(target, graph)


def save_wallet_clusters(clusters: dict[str, Any], path: Path | str | None = None, *, settings: Any | None = None) -> Path:
    target = _path_or_default(path, wallet_cluster_output_path(settings=settings))
    return write_json(target, clusters)


def append_wallet_graph_event(event: dict[str, Any], path: Path | str | None = None, *, settings: Any | None = None) -> Path:
    target = _path_or_default(path, wallet_graph_events_path(settings=settings))
    return append_jsonl(target, event)


def persist_wallet_cluster_artifacts(
    *,
    graph: dict[str, Any],
    clusters: dict[str, Any],
    settings: Any | None = None,
    graph_path: Path | str | None = None,
    cluster_path: Path | str | None = None,
    event_path: Path | str | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    graph_target = save_wallet_graph(graph, graph_path, settings=settings)
    cluster_target = save_wallet_clusters(clusters, cluster_path, settings=settings)
    event_target = _path_or_default(event_path, wallet_graph_events_path(settings=settings))
    for event in events or []:
        append_wallet_graph_event(event, event_target)
    return {"graph_path": graph_target, "cluster_path": cluster_target, "event_path": event_target}


def build_and_persist_wallet_clusters(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    settings: Any | None = None,
    metadata: dict[str, Any] | None = None,
    graph_path: Path | str | None = None,
    cluster_path: Path | str | None = None,
    event_path: Path | str | None = None,
    min_weight: float | None = None,
) -> dict[str, Any]:
    graph = build_wallet_graph(participants, creator_wallet=creator_wallet, metadata=metadata)
    threshold = float(min_weight if min_weight is not None else getattr(settings, "WALLET_GRAPH_EDGE_MIN_WEIGHT", 0.5))
    clusters = derive_wallet_clusters(graph, min_weight=threshold)
    scope = _metadata_scope_values(metadata)
    events = [
        {"event": "wallet_graph_build_started", **scope},
        {
            "event": "wallet_graph_completed",
            "status": "ok" if graph.get("summary", {}).get("edge_count", 0) > 0 else "partial",
            "node_count": graph.get("summary", {}).get("node_count", 0),
            "edge_count": graph.get("summary", {}).get("edge_count", 0),
            "cluster_count": clusters.get("summary", {}).get("cluster_count", 0),
            **scope,
        },
    ]
    persist_wallet_cluster_artifacts(
        graph=graph,
        clusters=clusters,
        settings=settings,
        graph_path=graph_path,
        cluster_path=cluster_path,
        event_path=event_path,
        events=events,
    )
    return {"graph": graph, "clusters": clusters}
