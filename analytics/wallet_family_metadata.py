"""Deterministic, conservative wallet family metadata derivation helpers."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from utils.clock import utc_now_iso
from utils.logger import log_info, log_warning
from utils.provenance_enums import (
    MISSING_PROVENANCE_ORIGIN,
    WALLET_FAMILY_PROVENANCE_ORIGINS,
    normalize_provenance_origin,
)

WALLET_FAMILY_METADATA_CONTRACT_VERSION = "wallet_family_metadata.v1"

WALLET_FAMILY_ORIGINS = set(WALLET_FAMILY_PROVENANCE_ORIGINS)
WALLET_FAMILY_STATUSES = {"ok", "partial", "missing", "failed"}

REASON_EXPLICIT_FAMILY_HINT = "explicit_family_hint"
REASON_EXPLICIT_INDEPENDENT_FAMILY_HINT = "explicit_independent_family_hint"
REASON_SHARED_CLUSTER = "shared_cluster_membership"
REASON_SHARED_FUNDER = "shared_funder"
REASON_REPEATED_LAUNCH = "repeated_launch_coappearance"
REASON_SHARED_LINKAGE_GROUP = "shared_linkage_group"
REASON_SHARED_LINKAGE_PEER = "linked_wallet_peer_reference"
REASON_CREATOR_LINK = "creator_link_overlap"
REASON_MISSING = "wallet_family_missing"
REASON_PARTIAL = "wallet_family_partial"
REASON_MALFORMED = "wallet_family_malformed"

_FUNDING_KEYS = (
    "funder",
    "funding_source",
    "funding_wallet",
    "source_wallet",
    "source_owner",
    "funded_by",
    "shared_funder",
)
_CLUSTER_KEYS = ("wallet_cluster_id", "cluster_id", "shared_cluster_id")
_LAUNCH_KEYS = (
    "launch_id",
    "launch_group",
    "launch_key",
    "launch_cluster",
    "same_launch_tag",
    "group_key",
    "group_id",
    "bundle_id",
    "cohort_id",
    "window_id",
    "slot_group",
)
_FAMILY_HINT_KEYS = ("wallet_family_hint", "family_hint", "family_group_hint", "registry_family_hint")
_INDEPENDENT_FAMILY_HINT_KEYS = (
    "independent_family_hint",
    "wallet_independent_family_hint",
    "strict_family_hint",
)
_LINKAGE_GROUP_KEYS = ("linkage_group", "linkage_hint", "linked_group_id")
_LINKED_WALLET_KEYS = ("linked_wallets", "wallet_family_peers", "linkage_peer_wallets")
_CREATOR_LINK_KEYS = (
    "creator_linked",
    "creator_overlap",
    "creator_related",
    "dev_linked",
    "dev_overlap",
    "wallet_family_creator_link_flag",
)


@dataclass(frozen=True)
class _WalletEvidence:
    wallet: str
    cluster_ids: tuple[str, ...]
    funders: tuple[str, ...]
    launch_groups: tuple[str, ...]
    family_hints: tuple[str, ...]
    independent_family_hints: tuple[str, ...]
    linkage_groups: tuple[str, ...]
    linked_wallets: tuple[str, ...]
    creator_link_flag: bool
    warnings: tuple[str, ...]


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


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return None
    text = str(value).strip()
    return text or None


def _safe_wallet(value: Any) -> str | None:
    text = _safe_text(value)
    if not text or any(ch.isspace() for ch in text):
        return None
    return text


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _normalize_values(values: list[Any], *, wallet: bool = False) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            if wallet:
                candidate = _safe_wallet(
                    value.get("wallet")
                    or value.get("wallet_address")
                    or value.get("address")
                    or value.get("owner")
                )
            else:
                candidate = _safe_text(next(iter(value.values()), None))
        else:
            candidate = _safe_wallet(value) if wallet else _safe_text(value)
        if candidate:
            normalized.add(candidate)
    return tuple(sorted(normalized))


def _stable_family_id(prefix: str, wallets: list[str]) -> str:
    canonical = "|".join(sorted(wallets))
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def assign_wallet_family_ids(groups: list[list[str]], *, prefix: str = "wallet_family") -> dict[str, str]:
    """Assign deterministic family ids from canonical sorted members."""

    mapping: dict[str, str] = {}
    for members in sorted((sorted(set(group)) for group in groups if len(set(group)) >= 2), key=lambda item: tuple(item)):
        family_id = _stable_family_id(prefix, members)
        for wallet in members:
            mapping[wallet] = family_id
    return mapping


def _member_groups(mapping: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for wallet, family_id in sorted(mapping.items()):
        groups[family_id].append(wallet)
    return {family_id: sorted(wallets) for family_id, wallets in sorted(groups.items())}


def _origin_for_sources(sources: set[str]) -> str:
    normalized = {
        normalize_provenance_origin(source)
        for source in sources
        if normalize_provenance_origin(source) in WALLET_FAMILY_PROVENANCE_ORIGINS
        and normalize_provenance_origin(source) != MISSING_PROVENANCE_ORIGIN
    }
    if not normalized:
        return "missing"
    if len(normalized) > 1:
        return "mixed_evidence"
    return next(iter(normalized))


def _status_for_confidence(confidence: float | None, *, has_family: bool, malformed: bool = False) -> str:
    if malformed and not has_family:
        return "failed"
    if not has_family or confidence is None or confidence <= 0:
        return "missing"
    if confidence < 0.7:
        return "partial"
    return "ok"


def _extract_wallet_evidence(record: dict[str, Any]) -> _WalletEvidence | None:
    wallet = _safe_wallet(record.get("wallet") or record.get("wallet_address") or record.get("address"))
    if not wallet:
        return None

    warnings: set[str] = set()
    source_records = record.get("source_records") if isinstance(record.get("source_records"), list) else []

    def collect(keys: tuple[str, ...], *, wallet_values: bool = False) -> tuple[str, ...]:
        values: list[Any] = []
        for key in keys:
            values.extend(_iter_values(record.get(key)))
        for source_record in source_records:
            if not isinstance(source_record, dict):
                warnings.add(REASON_MALFORMED)
                continue
            for key in keys:
                values.extend(_iter_values(source_record.get(key)))
        return _normalize_values(values, wallet=wallet_values)

    creator_link_flag = any(_boolish(record.get(key)) for key in _CREATOR_LINK_KEYS)
    for source_record in source_records:
        if not isinstance(source_record, dict):
            continue
        creator_link_flag = creator_link_flag or any(_boolish(source_record.get(key)) for key in _CREATOR_LINK_KEYS)

    family_hints = collect(_FAMILY_HINT_KEYS)
    independent_family_hints = collect(_INDEPENDENT_FAMILY_HINT_KEYS)
    linked_wallets = tuple(wallet_id for wallet_id in collect(_LINKED_WALLET_KEYS, wallet_values=True) if wallet_id != wallet)

    raw_linkage_confidence = record.get("linkage_confidence")
    if raw_linkage_confidence not in (None, ""):
        try:
            creator_link_flag = creator_link_flag or float(raw_linkage_confidence) >= 0.65
        except (TypeError, ValueError):
            warnings.add(REASON_MALFORMED)

    return _WalletEvidence(
        wallet=wallet,
        cluster_ids=collect(_CLUSTER_KEYS),
        funders=collect(_FUNDING_KEYS, wallet_values=True),
        launch_groups=collect(_LAUNCH_KEYS),
        family_hints=family_hints,
        independent_family_hints=independent_family_hints,
        linkage_groups=collect(_LINKAGE_GROUP_KEYS),
        linked_wallets=linked_wallets,
        creator_link_flag=creator_link_flag,
        warnings=tuple(sorted(warnings)),
    )


def _pairwise_evidence(left: _WalletEvidence, right: _WalletEvidence) -> dict[str, Any]:
    reason_codes: set[str] = set()
    sources: set[str] = set()
    broad_confidence = 0.0
    strict_confidence = 0.0

    shared_family_hints = set(left.family_hints) & set(right.family_hints)
    if shared_family_hints:
        reason_codes.add(REASON_EXPLICIT_FAMILY_HINT)
        sources.add("registry_evidence")
        broad_confidence += 0.6
        strict_confidence += 0.45

    shared_independent_hints = set(left.independent_family_hints) & set(right.independent_family_hints)
    if shared_independent_hints:
        reason_codes.add(REASON_EXPLICIT_INDEPENDENT_FAMILY_HINT)
        sources.add("registry_evidence")
        broad_confidence += 0.35
        strict_confidence += 0.55

    shared_clusters = set(left.cluster_ids) & set(right.cluster_ids)
    if shared_clusters:
        reason_codes.add(REASON_SHARED_CLUSTER)
        sources.add("graph_evidence")
        broad_confidence += 0.55
        strict_confidence += 0.35

    shared_funders = set(left.funders) & set(right.funders)
    if shared_funders:
        reason_codes.add(REASON_SHARED_FUNDER)
        sources.add("heuristic_evidence")
        broad_confidence += 0.25
        strict_confidence += 0.1

    shared_launches = set(left.launch_groups) & set(right.launch_groups)
    if len(shared_launches) >= 2:
        reason_codes.add(REASON_REPEATED_LAUNCH)
        sources.add("heuristic_evidence")
        broad_confidence += 0.3
        strict_confidence += 0.2
    elif len(shared_launches) == 1:
        sources.add("heuristic_evidence")
        broad_confidence += 0.1

    shared_linkage_groups = set(left.linkage_groups) & set(right.linkage_groups)
    if shared_linkage_groups:
        reason_codes.add(REASON_SHARED_LINKAGE_GROUP)
        sources.add("linkage_evidence")
        broad_confidence += 0.35
        strict_confidence += 0.25

    if right.wallet in set(left.linked_wallets) or left.wallet in set(right.linked_wallets):
        reason_codes.add(REASON_SHARED_LINKAGE_PEER)
        sources.add("linkage_evidence")
        broad_confidence += 0.35
        strict_confidence += 0.25

    if left.creator_link_flag and right.creator_link_flag:
        reason_codes.add(REASON_CREATOR_LINK)
        sources.add("linkage_evidence")
        broad_confidence += 0.2
        strict_confidence += 0.2

    broad_confidence = round(min(1.0, broad_confidence), 6)
    strict_confidence = round(min(1.0, strict_confidence), 6)
    return {
        "wallets": (left.wallet, right.wallet),
        "broad_confidence": broad_confidence,
        "strict_confidence": strict_confidence,
        "reason_codes": sorted(reason_codes),
        "origin": _origin_for_sources(sources),
        "shared_funder_flag": bool(shared_funders),
        "creator_link_flag": left.creator_link_flag and right.creator_link_flag,
    }


def summarize_wallet_family_metadata(
    wallet_records: list[dict[str, Any]],
    family_assignments: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = warnings or []
    statuses = [str(record.get("wallet_family_status") or "missing") for record in wallet_records]
    origins = [normalize_provenance_origin(record.get("wallet_family_origin")) for record in wallet_records]
    confidence_values = [float(record.get("wallet_family_confidence") or 0.0) for record in wallet_records if record.get("wallet_family_confidence") is not None]
    broad_ids = {str(record.get("wallet_family_id")) for record in wallet_records if record.get("wallet_family_id")}
    independent_ids = {str(record.get("independent_family_id")) for record in wallet_records if record.get("independent_family_id")}

    return {
        "wallet_count": len(wallet_records),
        "family_count": len(broad_ids),
        "independent_family_count": len(independent_ids),
        "assigned_wallets": sum(1 for record in wallet_records if record.get("wallet_family_id")),
        "independent_wallets": sum(1 for record in wallet_records if record.get("independent_family_id")),
        "strong_assignments": sum(1 for value in confidence_values if value >= 0.7),
        "weak_assignments": sum(1 for value in confidence_values if 0 < value < 0.7),
        "missing_assignments": statuses.count("missing"),
        "failed_assignments": statuses.count("failed"),
        "partial_assignments": statuses.count("partial"),
        "ok_assignments": statuses.count("ok"),
        "origins": {origin: origins.count(origin) for origin in sorted(set(origins))},
        "warning_count": len(warnings),
        "family_assignment_rows": len(family_assignments),
    }


def derive_wallet_family_metadata(
    wallet_records: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Derive conservative wallet family metadata from registry-like wallet records."""

    records = list(wallet_records or [])
    timestamp = generated_at or utc_now_iso()
    log_info("wallet_family_metadata_started", wallet_count=len(records))

    warnings: list[str] = []
    enriched_records: list[dict[str, Any]] = []
    evidence_by_wallet: dict[str, _WalletEvidence] = {}
    malformed_count = 0

    for record in records:
        if not isinstance(record, dict):
            malformed_count += 1
            continue
        evidence = _extract_wallet_evidence(record)
        if evidence is None:
            malformed_count += 1
            wallet = _safe_text(record.get("wallet") or record.get("wallet_address") or "") or ""
            enriched_records.append(
                {
                    **record,
                    "wallet": wallet,
                    "wallet_family_id": None,
                    "independent_family_id": None,
                    "wallet_family_confidence": 0.0,
                    "wallet_family_origin": "missing",
                    "wallet_family_reason_codes": [REASON_MALFORMED],
                    "wallet_cluster_id": None,
                    "wallet_family_member_count": 0,
                    "wallet_family_shared_funder_flag": False,
                    "wallet_family_creator_link_flag": False,
                    "wallet_family_status": "failed",
                }
            )
            continue
        evidence_by_wallet[evidence.wallet] = evidence
        warnings.extend(evidence.warnings)
        enriched_records.append(dict(record, wallet=evidence.wallet))

    wallets = sorted(evidence_by_wallet)
    pairwise: dict[tuple[str, str], dict[str, Any]] = {}
    broad_union = _UnionFind(wallets)
    strict_union = _UnionFind(wallets)

    for index, left_wallet in enumerate(wallets):
        left = evidence_by_wallet[left_wallet]
        for right_wallet in wallets[index + 1 :]:
            right = evidence_by_wallet[right_wallet]
            pair = _pairwise_evidence(left, right)
            if pair["broad_confidence"] <= 0:
                continue
            pairwise[(left_wallet, right_wallet)] = pair
            if pair["broad_confidence"] >= 0.25:
                broad_union.union(left_wallet, right_wallet)
            if pair["strict_confidence"] >= 0.7:
                strict_union.union(left_wallet, right_wallet)

    broad_groups: dict[str, list[str]] = defaultdict(list)
    strict_groups: dict[str, list[str]] = defaultdict(list)
    for wallet in wallets:
        broad_groups[broad_union.find(wallet)].append(wallet)
        strict_groups[strict_union.find(wallet)].append(wallet)

    broad_id_map = assign_wallet_family_ids([group for group in broad_groups.values() if len(group) >= 2], prefix="wallet_family")
    strict_id_map = assign_wallet_family_ids([group for group in strict_groups.values() if len(group) >= 2], prefix="independent_family")

    broad_group_by_id = _member_groups(broad_id_map)
    strict_group_by_id = _member_groups(strict_id_map)
    strict_id_by_members = {tuple(members): family_id for family_id, members in strict_group_by_id.items()}

    family_assignments: list[dict[str, Any]] = []
    family_summaries: list[dict[str, Any]] = []

    for family_id, members in broad_group_by_id.items():
        reasons: set[str] = set()
        origins: set[str] = set()
        confidence_values: list[float] = []
        shared_funder_flag = False
        creator_link_flag = False
        cluster_ids: set[str] = set()
        nested_independent_ids: set[str] = set()

        for idx, left_wallet in enumerate(members):
            cluster_ids.update(evidence_by_wallet[left_wallet].cluster_ids)
            if strict_id_map.get(left_wallet):
                nested_independent_ids.add(strict_id_map[left_wallet])
            for right_wallet in members[idx + 1 :]:
                pair = pairwise.get((left_wallet, right_wallet)) or pairwise.get((right_wallet, left_wallet))
                if not pair:
                    continue
                reasons.update(pair["reason_codes"])
                if pair["origin"] != "missing":
                    origins.add(pair["origin"])
                confidence_values.append(float(pair["broad_confidence"]))
                shared_funder_flag = shared_funder_flag or bool(pair["shared_funder_flag"])
                creator_link_flag = creator_link_flag or bool(pair["creator_link_flag"])

        family_confidence = round(max(confidence_values), 6) if confidence_values else 0.0
        status = _status_for_confidence(family_confidence, has_family=True)
        assignment = {
            "wallet_family_id": family_id,
            "family_type": "wallet_family",
            "member_wallets": members,
            "member_count": len(members),
            "wallet_family_confidence": family_confidence,
            "wallet_family_origin": _origin_for_sources(origins),
            "wallet_family_reason_codes": sorted(reasons) or [REASON_PARTIAL],
            "wallet_cluster_ids": sorted(cluster_ids),
            "wallet_family_shared_funder_flag": shared_funder_flag,
            "wallet_family_creator_link_flag": creator_link_flag,
            "wallet_family_status": status,
            "independent_family_ids": sorted(nested_independent_ids),
        }
        family_assignments.append(assignment)
        family_summaries.append(
            {
                "wallet_family_id": family_id,
                "member_count": len(members),
                "independent_family_count": len(nested_independent_ids),
                "wallet_family_confidence": family_confidence,
                "wallet_family_origin": assignment["wallet_family_origin"],
                "wallet_family_status": status,
            }
        )

    for members, family_id in sorted(strict_id_by_members.items()):
        reasons: set[str] = set()
        origins: set[str] = set()
        confidence_values: list[float] = []
        for idx, left_wallet in enumerate(members):
            for right_wallet in members[idx + 1 :]:
                pair = pairwise.get((left_wallet, right_wallet)) or pairwise.get((right_wallet, left_wallet))
                if not pair:
                    continue
                reasons.update(pair["reason_codes"])
                if pair["origin"] != "missing":
                    origins.add(pair["origin"])
                confidence_values.append(float(pair["strict_confidence"]))
        family_assignments.append(
            {
                "wallet_family_id": family_id,
                "family_type": "independent_family",
                "member_wallets": list(members),
                "member_count": len(members),
                "wallet_family_confidence": round(max(confidence_values), 6) if confidence_values else 0.0,
                "wallet_family_origin": _origin_for_sources(origins),
                "wallet_family_reason_codes": sorted(reasons) or [REASON_PARTIAL],
                "wallet_family_shared_funder_flag": REASON_SHARED_FUNDER in reasons,
                "wallet_family_creator_link_flag": REASON_CREATOR_LINK in reasons,
                "wallet_family_status": _status_for_confidence(max(confidence_values) if confidence_values else 0.0, has_family=True),
            }
        )

    by_wallet_component_confidence: dict[str, float] = defaultdict(float)
    by_wallet_component_reasons: dict[str, set[str]] = defaultdict(set)
    by_wallet_component_origins: dict[str, set[str]] = defaultdict(set)
    by_wallet_shared_funder: dict[str, bool] = defaultdict(bool)
    by_wallet_creator_link: dict[str, bool] = defaultdict(bool)

    for (left_wallet, right_wallet), pair in pairwise.items():
        by_wallet_component_confidence[left_wallet] = max(by_wallet_component_confidence[left_wallet], float(pair["broad_confidence"]))
        by_wallet_component_confidence[right_wallet] = max(by_wallet_component_confidence[right_wallet], float(pair["broad_confidence"]))
        by_wallet_component_reasons[left_wallet].update(pair["reason_codes"])
        by_wallet_component_reasons[right_wallet].update(pair["reason_codes"])
        if pair["origin"] != "missing":
            by_wallet_component_origins[left_wallet].add(pair["origin"])
            by_wallet_component_origins[right_wallet].add(pair["origin"])
        by_wallet_shared_funder[left_wallet] = by_wallet_shared_funder[left_wallet] or bool(pair["shared_funder_flag"])
        by_wallet_shared_funder[right_wallet] = by_wallet_shared_funder[right_wallet] or bool(pair["shared_funder_flag"])
        by_wallet_creator_link[left_wallet] = by_wallet_creator_link[left_wallet] or bool(pair["creator_link_flag"])
        by_wallet_creator_link[right_wallet] = by_wallet_creator_link[right_wallet] or bool(pair["creator_link_flag"])

    final_wallet_records: list[dict[str, Any]] = []
    for record in enriched_records:
        wallet = str(record.get("wallet") or "")
        evidence = evidence_by_wallet.get(wallet)
        family_id = broad_id_map.get(wallet)
        independent_family_id = strict_id_map.get(wallet)
        confidence = round(by_wallet_component_confidence.get(wallet, 0.0), 6)
        malformed = REASON_MALFORMED in set((evidence.warnings if evidence else ()))
        has_family = family_id is not None
        status = _status_for_confidence(confidence, has_family=has_family, malformed=malformed)
        if not has_family and status == "missing":
            log_info("wallet_family_missing", wallet=wallet)
        elif status == "partial":
            log_info("wallet_family_partial", wallet=wallet, wallet_family_id=family_id, confidence=confidence)

        member_count = len(broad_group_by_id.get(family_id, [])) if family_id else 0
        wallet_cluster_id = None
        if evidence and evidence.cluster_ids:
            wallet_cluster_id = evidence.cluster_ids[0] if len(evidence.cluster_ids) == 1 else evidence.cluster_ids[0]
        final_wallet_records.append(
            {
                **record,
                "wallet_family_id": family_id,
                "independent_family_id": independent_family_id,
                "wallet_family_confidence": confidence,
                "wallet_family_origin": _origin_for_sources(by_wallet_component_origins.get(wallet, set())),
                "wallet_family_reason_codes": sorted(by_wallet_component_reasons.get(wallet, set())) or [REASON_MISSING],
                "wallet_cluster_id": wallet_cluster_id,
                "wallet_family_member_count": member_count,
                "wallet_family_shared_funder_flag": bool(by_wallet_shared_funder.get(wallet, False)),
                "wallet_family_creator_link_flag": bool(by_wallet_creator_link.get(wallet, False) or (evidence.creator_link_flag if evidence else False)),
                "wallet_family_status": status,
            }
        )

    if malformed_count:
        warning = f"malformed_wallet_records={malformed_count}"
        warnings.append(warning)
        log_warning("wallet_family_failed", malformed_records=malformed_count)

    warnings = sorted({warning for warning in warnings if warning})
    summary = summarize_wallet_family_metadata(final_wallet_records, family_assignments, warnings)
    log_info(
        "wallet_family_evidence_derived",
        wallet_count=len(final_wallet_records),
        family_count=summary["family_count"],
        warnings=len(warnings),
    )
    log_info(
        "wallet_family_ids_assigned",
        family_count=summary["family_count"],
        independent_family_count=summary["independent_family_count"],
        strong_assignments=summary["strong_assignments"],
        weak_assignments=summary["weak_assignments"],
    )
    log_info(
        "wallet_family_metadata_completed",
        wallet_count=summary["wallet_count"],
        family_count=summary["family_count"],
        provenance_mix=summary["origins"],
    )

    return {
        "contract_version": WALLET_FAMILY_METADATA_CONTRACT_VERSION,
        "generated_at": timestamp,
        "wallet_records": final_wallet_records,
        "family_assignments": sorted(
            family_assignments,
            key=lambda item: (str(item.get("family_type") or ""), str(item.get("wallet_family_id") or "")),
        ),
        "family_summaries": sorted(family_summaries, key=lambda item: str(item.get("wallet_family_id") or "")),
        "warnings": warnings,
        "summary": summary,
    }


__all__ = [
    "WALLET_FAMILY_METADATA_CONTRACT_VERSION",
    "assign_wallet_family_ids",
    "derive_wallet_family_metadata",
    "summarize_wallet_family_metadata",
]
