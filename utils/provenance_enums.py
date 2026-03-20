"""Shared canonical provenance enum helpers for emitted artifacts."""

from __future__ import annotations

from typing import Any, Iterable

DIRECT_EVIDENCE_ORIGIN = "direct_evidence"
GRAPH_EVIDENCE_ORIGIN = "graph_evidence"
HEURISTIC_EVIDENCE_ORIGIN = "heuristic_evidence"
REGISTRY_EVIDENCE_ORIGIN = "registry_evidence"
LINKAGE_EVIDENCE_ORIGIN = "linkage_evidence"
MIXED_EVIDENCE_ORIGIN = "mixed_evidence"
MISSING_PROVENANCE_ORIGIN = "missing"

CANONICAL_PROVENANCE_ORIGINS = frozenset(
    {
        DIRECT_EVIDENCE_ORIGIN,
        GRAPH_EVIDENCE_ORIGIN,
        HEURISTIC_EVIDENCE_ORIGIN,
        REGISTRY_EVIDENCE_ORIGIN,
        LINKAGE_EVIDENCE_ORIGIN,
        MIXED_EVIDENCE_ORIGIN,
        MISSING_PROVENANCE_ORIGIN,
    }
)

LEGACY_PROVENANCE_ALIASES = {
    "real_evidence": DIRECT_EVIDENCE_ORIGIN,
    "raw_bundles": DIRECT_EVIDENCE_ORIGIN,
    "graph_backed": GRAPH_EVIDENCE_ORIGIN,
    "heuristic": HEURISTIC_EVIDENCE_ORIGIN,
    "heuristic_fallback": HEURISTIC_EVIDENCE_ORIGIN,
}

BUNDLE_PROVENANCE_ORIGINS = frozenset(
    {
        DIRECT_EVIDENCE_ORIGIN,
        HEURISTIC_EVIDENCE_ORIGIN,
        MISSING_PROVENANCE_ORIGIN,
    }
)

CLUSTER_PROVENANCE_ORIGINS = frozenset(
    {
        GRAPH_EVIDENCE_ORIGIN,
        HEURISTIC_EVIDENCE_ORIGIN,
        MISSING_PROVENANCE_ORIGIN,
    }
)

LINKAGE_PROVENANCE_ORIGINS = frozenset(
    {
        GRAPH_EVIDENCE_ORIGIN,
        HEURISTIC_EVIDENCE_ORIGIN,
        MIXED_EVIDENCE_ORIGIN,
        MISSING_PROVENANCE_ORIGIN,
    }
)

WALLET_FAMILY_PROVENANCE_ORIGINS = frozenset(
    {
        GRAPH_EVIDENCE_ORIGIN,
        LINKAGE_EVIDENCE_ORIGIN,
        REGISTRY_EVIDENCE_ORIGIN,
        HEURISTIC_EVIDENCE_ORIGIN,
        MIXED_EVIDENCE_ORIGIN,
        MISSING_PROVENANCE_ORIGIN,
    }
)


PROVENANCE_ALLOWED_BY_FIELD = {
    "bundle_metric_origin": BUNDLE_PROVENANCE_ORIGINS,
    "cluster_metric_origin": CLUSTER_PROVENANCE_ORIGINS,
    "linkage_metric_origin": LINKAGE_PROVENANCE_ORIGINS,
    "wallet_family_origin": WALLET_FAMILY_PROVENANCE_ORIGINS,
}


def normalize_provenance_origin(value: Any) -> str:
    if value is None:
        return MISSING_PROVENANCE_ORIGIN
    text = str(value).strip().lower()
    if not text:
        return MISSING_PROVENANCE_ORIGIN
    return LEGACY_PROVENANCE_ALIASES.get(text, text)


def validate_provenance_origin(value: Any, *, allowed: Iterable[str]) -> str:
    normalized = normalize_provenance_origin(value)
    allowed_set = {str(item).strip() for item in allowed}
    if normalized not in allowed_set:
        raise ValueError(f"unsupported provenance origin: {value!r}")
    return normalized
