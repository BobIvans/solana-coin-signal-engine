"""Conservative creator/dev/funder linkage scoring for early launch manipulation risk."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from analytics.funder_sanitization import load_funder_ignorelist, sanitize_funder_set
from utils.logger import log_error, log_info, log_warning
from utils.provenance_enums import LINKAGE_PROVENANCE_ORIGINS, validate_provenance_origin

LINKAGE_REASON_DIRECT_CREATOR_BUYER = "creator_buyer_direct_link"
LINKAGE_REASON_DIRECT_DEV_BUYER = "dev_buyer_direct_link"
LINKAGE_REASON_CREATOR_DEV_SHARED_FUNDER = "creator_dev_same_funder"
LINKAGE_REASON_CREATOR_BUYER_SHARED_FUNDER = "creator_buyer_same_funder"
LINKAGE_REASON_DEV_BUYER_SHARED_FUNDER = "dev_buyer_same_funder"
LINKAGE_REASON_CREATOR_CLUSTER_OVERLAP = "creator_cluster_overlap"
LINKAGE_REASON_DEV_CLUSTER_OVERLAP = "dev_cluster_overlap"
LINKAGE_REASON_SHARED_LAUNCH_GROUP = "shared_launch_group"
LINKAGE_REASON_SHARED_CLUSTER_ID = "shared_cluster_id"
LINKAGE_REASON_SHARED_FUNDER_OVERLAP = "shared_funder_overlap"
LINKAGE_REASON_PARTIAL = "linkage_partial"
LINKAGE_REASON_MISSING = "linkage_missing"
LINKAGE_REASON_MALFORMED = "linkage_malformed"


def _safe_wallet(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, dict)):
        return None
    wallet = str(value).strip()
    if not wallet or any(ch.isspace() for ch in wallet):
        return None
    return wallet


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _participant_wallet(participant: dict[str, Any]) -> str | None:
    for key in ("wallet", "wallet_address", "address", "owner", "signer", "fee_payer", "actor"):
        wallet = _safe_wallet(participant.get(key))
        if wallet:
            return wallet
    return None


def _normalize_wallet_list(values: Any) -> list[str]:
    wallets: list[str] = []
    seen: set[str] = set()
    for item in _iter_values(values):
        if isinstance(item, dict):
            wallet = _participant_wallet(item)
        else:
            wallet = _safe_wallet(item)
        if wallet and wallet not in seen:
            seen.add(wallet)
            wallets.append(wallet)
    return wallets


def _normalize_wallet_sets(value: Any, *, wallet: bool = True) -> set[str]:
    out: set[str] = set()
    for item in _iter_values(value):
        normalized = _safe_wallet(item) if wallet else _safe_text(item)
        if normalized:
            out.add(normalized)
    return out


def _sanitize_funders(funders: set[str]) -> dict[str, Any]:
    return sanitize_funder_set(
        funders,
        ignored_funders=load_funder_ignorelist(Path("config/funder_ignorelist.json")),
        sanitize_common_sources=True,
    )


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def _score_count(count: int, *, cap: int = 3) -> float:
    if count <= 0:
        return 0.0
    return min(count, cap) / float(cap)


def _metric_origin(*, graph_present: bool, heuristic_present: bool) -> str:
    if graph_present and heuristic_present:
        origin = "mixed_evidence"
    elif graph_present:
        origin = "graph_evidence"
    elif heuristic_present:
        origin = "heuristic_evidence"
    else:
        origin = "missing"
    return validate_provenance_origin(origin, allowed=LINKAGE_PROVENANCE_ORIGINS)


def derive_linkage_evidence(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    dev_wallet: str | None = None,
    early_buyer_wallets: list[str] | None = None,
    cluster_ids_by_wallet: dict[str, str] | None = None,
    token_address: str | None = None,
    pair_address: str | None = None,
) -> dict[str, Any]:
    """Normalize creator/dev/funder linkage evidence from shallow participant records."""

    token_ref = _safe_text(token_address) or ""
    pair_ref = _safe_text(pair_address) or ""
    creator = _safe_wallet(creator_wallet)
    dev = _safe_wallet(dev_wallet)
    explicit_early_buyers = _normalize_wallet_list(early_buyer_wallets)
    warnings: list[str] = []
    reason_codes: set[str] = set()

    log_info(
        "linkage_scoring_started",
        token_address=token_ref,
        pair_address=pair_ref,
        creator_wallet_present=creator is not None,
        dev_wallet_present=dev is not None,
        participants=len(participants or []),
    )

    normalized: dict[str, dict[str, Any]] = {}
    malformed_records = 0
    raw_cluster_ids = cluster_ids_by_wallet or {}
    for participant in participants:
        if not isinstance(participant, dict):
            malformed_records += 1
            continue
        wallet = _participant_wallet(participant)
        if not wallet:
            malformed_records += 1
            continue
        bucket = normalized.setdefault(
            wallet,
            {
                "funders": set(),
                "launch_groups": set(),
                "cluster_ids": set(),
                "direct_creator_link": False,
                "direct_dev_link": False,
                "creator_hint": False,
            },
        )
        bucket["funders"].update(
            _normalize_wallet_sets(
                [
                    participant.get("funder"),
                    participant.get("funding_source"),
                    participant.get("funding_wallet"),
                    participant.get("source_wallet"),
                    participant.get("source_owner"),
                    participant.get("funded_by"),
                    participant.get("shared_funder"),
                    participant.get("creator_funder"),
                    participant.get("dev_funder"),
                ]
            )
        )
        bucket["launch_groups"].update(
            _normalize_wallet_sets(
                [
                    participant.get("launch_id"),
                    participant.get("launch_group"),
                    participant.get("launch_key"),
                    participant.get("launch_cluster"),
                    participant.get("same_launch_tag"),
                    participant.get("group_key"),
                    participant.get("group_id"),
                    participant.get("bundle_id"),
                    participant.get("cohort_id"),
                    participant.get("window_id"),
                    participant.get("slot_group"),
                    participant.get("shared_launch_group"),
                ],
                wallet=False,
            )
        )
        bucket["cluster_ids"].update(
            _normalize_wallet_sets(
                [
                    participant.get("cluster_id"),
                    participant.get("shared_cluster_id"),
                    raw_cluster_ids.get(wallet),
                ],
                wallet=False,
            )
        )
        bucket["direct_creator_link"] = bucket["direct_creator_link"] or any(
            _boolish(participant.get(key))
            for key in (
                "creator_linked",
                "creator_overlap",
                "creator_related",
                "direct_creator_link",
            )
        )
        bucket["direct_dev_link"] = bucket["direct_dev_link"] or any(
            _boolish(participant.get(key))
            for key in ("dev_linked", "dev_overlap", "direct_dev_link")
        )
        bucket["creator_hint"] = bucket["creator_hint"] or any(
            _boolish(participant.get(key)) for key in ("creator_linked", "creator_overlap")
        )

    if creator and creator in normalized:
        normalized[creator]["direct_creator_link"] = True
        normalized[creator]["creator_hint"] = True
    if dev and dev in normalized:
        normalized[dev]["direct_dev_link"] = True

    for bucket in normalized.values():
        sanitized = _sanitize_funders(set(bucket.get("funders", set())))
        bucket["sanitized_funders"] = set(sanitized["sanitized_funders"])
        bucket["ignored_funders"] = set(sanitized["ignored_funders"])
        bucket["funder_sanitization_applied"] = bool(sanitized["funder_sanitization_applied"])

    if not explicit_early_buyers:
        explicit_early_buyers = [wallet for wallet in normalized if wallet not in {creator, dev}]
    early_buyers = [wallet for wallet in explicit_early_buyers if wallet in normalized and wallet not in {creator, dev}]

    creator_raw_funders = set(normalized.get(creator, {}).get("funders", set())) if creator else set()
    dev_raw_funders = set(normalized.get(dev, {}).get("funders", set())) if dev else set()
    creator_funders = set(normalized.get(creator, {}).get("sanitized_funders", set())) if creator else set()
    dev_funders = set(normalized.get(dev, {}).get("sanitized_funders", set())) if dev else set()
    creator_clusters = set(normalized.get(creator, {}).get("cluster_ids", set())) if creator else set()
    dev_clusters = set(normalized.get(dev, {}).get("cluster_ids", set())) if dev else set()
    creator_launch_groups = set(normalized.get(creator, {}).get("launch_groups", set())) if creator else set()
    dev_launch_groups = set(normalized.get(dev, {}).get("launch_groups", set())) if dev else set()

    buyer_raw_funders: set[str] = set()
    buyer_funders: set[str] = set()
    buyer_funder_counts: dict[str, int] = defaultdict(int)
    buyer_clusters: set[str] = set()
    buyer_launch_groups: set[str] = set()
    direct_creator_links: list[str] = []
    direct_dev_links: list[str] = []
    creator_buyer_funder_overlap = 0
    dev_buyer_funder_overlap = 0
    creator_buyer_cluster_overlap = False
    dev_buyer_cluster_overlap = False
    shared_launch_groups: set[str] = set()
    shared_cluster_ids: set[str] = set()
    ignored_shared_funders: set[str] = set()

    for wallet in early_buyers:
        bucket = normalized.get(wallet, {})
        raw_funders = set(bucket.get("funders", set()))
        funders = set(bucket.get("sanitized_funders", set()))
        clusters = set(bucket.get("cluster_ids", set()))
        launches = set(bucket.get("launch_groups", set()))
        buyer_raw_funders.update(raw_funders)
        buyer_funders.update(funders)
        for funder in funders:
            buyer_funder_counts[funder] += 1
        buyer_clusters.update(clusters)
        buyer_launch_groups.update(launches)
        if bucket.get("direct_creator_link"):
            direct_creator_links.append(wallet)
        if bucket.get("direct_dev_link"):
            direct_dev_links.append(wallet)
        if creator_raw_funders and raw_funders & creator_raw_funders:
            ignored_shared_funders.update((raw_funders & creator_raw_funders) - (funders & creator_funders))
        if dev_raw_funders and raw_funders & dev_raw_funders:
            ignored_shared_funders.update((raw_funders & dev_raw_funders) - (funders & dev_funders))
        if creator_funders and funders & creator_funders:
            creator_buyer_funder_overlap += len(funders & creator_funders)
        if dev_funders and funders & dev_funders:
            dev_buyer_funder_overlap += len(funders & dev_funders)
        if creator_clusters and clusters & creator_clusters:
            creator_buyer_cluster_overlap = True
            shared_cluster_ids.update(clusters & creator_clusters)
        if dev_clusters and clusters & dev_clusters:
            dev_buyer_cluster_overlap = True
            shared_cluster_ids.update(clusters & dev_clusters)
        if creator_launch_groups and launches & creator_launch_groups:
            shared_launch_groups.update(launches & creator_launch_groups)
        if dev_launch_groups and launches & dev_launch_groups:
            shared_launch_groups.update(launches & dev_launch_groups)

    creator_dev_same_raw_funders = creator_raw_funders & dev_raw_funders
    creator_dev_same_funders = sorted(creator_funders & dev_funders)
    ignored_shared_funders.update(creator_dev_same_raw_funders - set(creator_dev_same_funders))
    repeated_buyer_funders = {funder for funder, count in buyer_funder_counts.items() if count >= 2}
    shared_funders = sorted((creator_funders & buyer_funders) | (dev_funders & buyer_funders) | set(creator_dev_same_funders) | repeated_buyer_funders)
    ignored_shared_funders.update(((creator_raw_funders & buyer_raw_funders) | (dev_raw_funders & buyer_raw_funders)) - set(shared_funders))
    if creator_buyer_cluster_overlap:
        shared_cluster_ids.update(creator_clusters & buyer_clusters)
    if dev_buyer_cluster_overlap:
        shared_cluster_ids.update(dev_clusters & buyer_clusters)
    shared_launch_groups.update((creator_launch_groups & buyer_launch_groups) | (dev_launch_groups & buyer_launch_groups) | (creator_launch_groups & dev_launch_groups))

    if creator_dev_same_funders:
        reason_codes.add(LINKAGE_REASON_CREATOR_DEV_SHARED_FUNDER)
    if shared_funders:
        reason_codes.add(LINKAGE_REASON_SHARED_FUNDER_OVERLAP)
    if creator_buyer_funder_overlap > 0:
        reason_codes.add(LINKAGE_REASON_CREATOR_BUYER_SHARED_FUNDER)
    if dev_buyer_funder_overlap > 0:
        reason_codes.add(LINKAGE_REASON_DEV_BUYER_SHARED_FUNDER)
    if direct_creator_links:
        reason_codes.add(LINKAGE_REASON_DIRECT_CREATOR_BUYER)
    if direct_dev_links:
        reason_codes.add(LINKAGE_REASON_DIRECT_DEV_BUYER)
    if creator_buyer_cluster_overlap:
        reason_codes.add(LINKAGE_REASON_CREATOR_CLUSTER_OVERLAP)
    if dev_buyer_cluster_overlap:
        reason_codes.add(LINKAGE_REASON_DEV_CLUSTER_OVERLAP)
    if shared_launch_groups:
        reason_codes.add(LINKAGE_REASON_SHARED_LAUNCH_GROUP)
    if shared_cluster_ids:
        reason_codes.add(LINKAGE_REASON_SHARED_CLUSTER_ID)

    graph_present = bool(shared_funders or shared_cluster_ids or creator_dev_same_funders)
    heuristic_present = bool(direct_creator_links or direct_dev_links or shared_launch_groups)

    valid_wallets = int(creator is not None) + int(dev is not None) + len(early_buyers)
    evidence_points = sum(
        1
        for flag in (
            bool(direct_creator_links),
            bool(direct_dev_links),
            bool(shared_funders),
            bool(shared_cluster_ids),
            bool(shared_launch_groups),
            bool(creator_dev_same_funders),
        )
        if flag
    )
    if valid_wallets == 0:
        status = "missing"
    elif malformed_records and not normalized:
        status = "failed"
    elif evidence_points == 0 and normalized:
        status = "partial" if (creator or dev or early_buyers) else "missing"
    else:
        status = "ok"

    if malformed_records:
        warnings.append(f"ignored_malformed_linkage_records={malformed_records}")
        reason_codes.add(LINKAGE_REASON_MALFORMED)
    if not (creator or dev or early_buyers):
        warnings.append("missing_creator_dev_and_early_buyer_wallets")
        reason_codes.add(LINKAGE_REASON_MISSING)
    elif evidence_points == 0:
        warnings.append("linkage_evidence_sparse")
        reason_codes.add(LINKAGE_REASON_PARTIAL)

    confidence_raw = 0.0
    if evidence_points > 0:
        confidence_raw = min(0.9, 0.22 + 0.12 * evidence_points)
        if graph_present and heuristic_present:
            confidence_raw += 0.08
        elif graph_present:
            confidence_raw += 0.04
        if malformed_records:
            confidence_raw -= 0.08
    elif status == "partial":
        confidence_raw = 0.18
    confidence = _bounded_score(confidence_raw)

    event_name = {
        "ok": "linkage_evidence_derived",
        "partial": "linkage_partial",
        "missing": "linkage_missing",
        "failed": "linkage_failed",
    }.get(status, "linkage_evidence_derived")
    log_fn = log_warning if status in {"partial", "missing"} else log_error if status == "failed" else log_info
    log_fn(
        event_name,
        token_address=token_ref,
        pair_address=pair_ref,
        creator_wallet_present=creator is not None,
        dev_wallet_present=dev is not None,
        early_buyer_count=len(early_buyers),
        shared_funder_count=len(shared_funders),
        ignored_shared_funder_count=len(ignored_shared_funders),
        reason_codes=sorted(reason_codes),
        confidence=confidence,
        warning=";".join(warnings) if warnings else None,
    )

    return {
        "creator_wallet": creator,
        "dev_wallet": dev,
        "early_buyer_wallets": early_buyers or None,
        "shared_funders": shared_funders or None,
        "sanitized_shared_funders": sorted(ignored_shared_funders) or None,
        "ignored_shared_funder_count": len(ignored_shared_funders),
        "funder_sanitization_applied": bool(ignored_shared_funders),
        "shared_launch_groups": sorted(shared_launch_groups) or None,
        "shared_cluster_ids": sorted(shared_cluster_ids) or None,
        "direct_creator_links": sorted(set(direct_creator_links)) or None,
        "direct_dev_links": sorted(set(direct_dev_links)) or None,
        "funder_overlap_count": len(shared_funders),
        "creator_dev_same_funder_flag": bool(creator_dev_same_funders) if (creator and dev) else None,
        "creator_buyer_same_funder_flag": bool(creator_buyer_funder_overlap) if creator and early_buyers else None,
        "dev_buyer_same_funder_flag": bool(dev_buyer_funder_overlap) if dev and early_buyers else None,
        "creator_cluster_overlap_flag": creator_buyer_cluster_overlap if creator and early_buyers else None,
        "dev_cluster_overlap_flag": dev_buyer_cluster_overlap if dev and early_buyers else None,
        "linkage_reason_codes": sorted(reason_codes),
        "linkage_confidence": confidence,
        "linkage_status": status,
        "linkage_warning": "; ".join(warnings) if warnings else None,
        "linkage_metric_origin": _metric_origin(graph_present=graph_present, heuristic_present=heuristic_present),
        "creator_funder_overlap_count": len(creator_funders & buyer_funders),
        "buyer_funder_overlap_count": len((creator_funders & buyer_funders) | (dev_funders & buyer_funders)),
    }


def score_creator_dev_funder_linkage(
    participants: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
    dev_wallet: str | None = None,
    early_buyer_wallets: list[str] | None = None,
    cluster_ids_by_wallet: dict[str, str] | None = None,
    token_address: str | None = None,
    pair_address: str | None = None,
    direct_overlap_weight: float = 0.55,
    funder_overlap_weight: float = 0.35,
    cluster_overlap_weight: float = 0.30,
) -> dict[str, Any]:
    """Score creator/dev/funder linkage using deterministic, bounded heuristics."""

    try:
        evidence = derive_linkage_evidence(
            participants,
            creator_wallet=creator_wallet,
            dev_wallet=dev_wallet,
            early_buyer_wallets=early_buyer_wallets,
            cluster_ids_by_wallet=cluster_ids_by_wallet,
            token_address=token_address,
            pair_address=pair_address,
        )

        if evidence["linkage_status"] == "failed":
            return summarize_linkage_score(
                {
                    **evidence,
                    "creator_dev_link_score": None,
                    "creator_buyer_link_score": None,
                    "dev_buyer_link_score": None,
                    "shared_funder_link_score": None,
                    "creator_cluster_link_score": None,
                    "cluster_dev_link_score": None,
                    "linkage_risk_score": None,
                    "creator_in_cluster_flag": None,
                }
            )

        direct_creator = 1.0 if evidence.get("direct_creator_links") else 0.0
        direct_dev = 1.0 if evidence.get("direct_dev_links") else 0.0
        shared_funder_component = _score_count(int(evidence.get("funder_overlap_count") or 0), cap=3)
        creator_cluster_component = 1.0 if evidence.get("creator_cluster_overlap_flag") else 0.0
        dev_cluster_component = 1.0 if evidence.get("dev_cluster_overlap_flag") else 0.0
        shared_launch_component = _score_count(len(evidence.get("shared_launch_groups") or []), cap=2)
        creator_dev_same_funder = 1.0 if evidence.get("creator_dev_same_funder_flag") else 0.0

        creator_dev_link_score = _bounded_score(
            direct_overlap_weight * 0.0
            + funder_overlap_weight * creator_dev_same_funder
            + cluster_overlap_weight * 0.0
            + 0.10 * shared_launch_component
        ) if evidence.get("creator_wallet") and evidence.get("dev_wallet") else None

        creator_buyer_link_score = _bounded_score(
            direct_overlap_weight * direct_creator
            + funder_overlap_weight * (1.0 if evidence.get("creator_buyer_same_funder_flag") else 0.0)
            + cluster_overlap_weight * creator_cluster_component
            + 0.10 * shared_launch_component
        ) if evidence.get("creator_wallet") and evidence.get("early_buyer_wallets") else None

        dev_buyer_link_score = _bounded_score(
            direct_overlap_weight * direct_dev
            + funder_overlap_weight * (1.0 if evidence.get("dev_buyer_same_funder_flag") else 0.0)
            + cluster_overlap_weight * dev_cluster_component
            + 0.10 * shared_launch_component
        ) if evidence.get("dev_wallet") and evidence.get("early_buyer_wallets") else None

        shared_funder_link_score = _bounded_score(
            0.60 * shared_funder_component + 0.40 * creator_dev_same_funder
        ) if evidence.get("funder_overlap_count") is not None else None

        creator_cluster_link_score = _bounded_score(
            0.70 * creator_cluster_component + 0.30 * shared_launch_component
        ) if evidence.get("creator_wallet") and evidence.get("early_buyer_wallets") else None

        cluster_dev_link_score = _bounded_score(
            0.70 * dev_cluster_component + 0.30 * shared_launch_component
        ) if evidence.get("dev_wallet") and evidence.get("early_buyer_wallets") else None

        risk_inputs = [
            (creator_buyer_link_score, 0.28),
            (dev_buyer_link_score, 0.24),
            (shared_funder_link_score, 0.20),
            (creator_cluster_link_score, 0.18),
            (creator_dev_link_score, 0.10),
        ]
        weighted = [(value, weight) for value, weight in risk_inputs if value is not None]
        if weighted:
            raw_risk = sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted)
            linkage_risk_score = _bounded_score(raw_risk * max(0.4, float(evidence.get("linkage_confidence") or 0.0)))
        else:
            linkage_risk_score = None

        if evidence.get("linkage_status") == "missing":
            linkage_risk_score = None

        derived_creator_cluster_flag = None
        if creator_cluster_link_score is not None and creator_cluster_link_score >= 0.65 and float(evidence.get("linkage_confidence") or 0.0) >= 0.55:
            derived_creator_cluster_flag = True

        scored = summarize_linkage_score(
            {
                **evidence,
                "creator_dev_link_score": creator_dev_link_score,
                "creator_buyer_link_score": creator_buyer_link_score,
                "dev_buyer_link_score": dev_buyer_link_score,
                "shared_funder_link_score": shared_funder_link_score,
                "creator_cluster_link_score": creator_cluster_link_score,
                "cluster_dev_link_score": cluster_dev_link_score,
                "linkage_risk_score": linkage_risk_score,
                "creator_in_cluster_flag": derived_creator_cluster_flag,
            }
        )
        log_info(
            "linkage_score_computed",
            token_address=_safe_text(token_address) or "",
            pair_address=_safe_text(pair_address) or "",
            linkage_risk_score=scored.get("linkage_risk_score"),
            linkage_confidence=scored.get("linkage_confidence"),
            reason_codes=scored.get("linkage_reason_codes"),
        )
        log_info(
            "linkage_completed",
            token_address=_safe_text(token_address) or "",
            pair_address=_safe_text(pair_address) or "",
            status=scored.get("linkage_status"),
            warning=scored.get("linkage_warning"),
        )
        return scored
    except Exception as exc:  # pragma: no cover - fail-open defensive path
        log_error(
            "linkage_failed",
            token_address=_safe_text(token_address) or "",
            pair_address=_safe_text(pair_address) or "",
            error=str(exc),
        )
        return summarize_linkage_score(
            {
                "creator_wallet": _safe_wallet(creator_wallet),
                "dev_wallet": _safe_wallet(dev_wallet),
                "early_buyer_wallets": _normalize_wallet_list(early_buyer_wallets),
                "shared_funders": None,
                "sanitized_shared_funders": None,
                "ignored_shared_funder_count": None,
                "funder_sanitization_applied": False,
                "shared_launch_groups": None,
                "shared_cluster_ids": None,
                "direct_creator_links": None,
                "direct_dev_links": None,
                "funder_overlap_count": None,
                "creator_dev_same_funder_flag": None,
                "creator_buyer_same_funder_flag": None,
                "dev_buyer_same_funder_flag": None,
                "creator_cluster_overlap_flag": None,
                "dev_cluster_overlap_flag": None,
                "linkage_reason_codes": [LINKAGE_REASON_MALFORMED],
                "linkage_confidence": 0.0,
                "linkage_status": "failed",
                "linkage_warning": str(exc),
                "linkage_metric_origin": "missing",
                "creator_funder_overlap_count": None,
                "buyer_funder_overlap_count": None,
                "creator_dev_link_score": None,
                "creator_buyer_link_score": None,
                "dev_buyer_link_score": None,
                "shared_funder_link_score": None,
                "creator_cluster_link_score": None,
                "cluster_dev_link_score": None,
                "linkage_risk_score": None,
                "creator_in_cluster_flag": None,
            }
        )


def summarize_linkage_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Return linkage scores with stable field defaults and sorted reason codes."""

    result = dict(payload)
    result["linkage_reason_codes"] = sorted({str(item) for item in _iter_values(payload.get("linkage_reason_codes")) if str(item).strip()})
    for field in (
        "creator_dev_link_score",
        "creator_buyer_link_score",
        "dev_buyer_link_score",
        "shared_funder_link_score",
        "creator_cluster_link_score",
        "cluster_dev_link_score",
        "linkage_risk_score",
        "linkage_confidence",
    ):
        if result.get(field) is not None:
            result[field] = _bounded_score(float(result[field]))
    for field in ("funder_overlap_count", "creator_funder_overlap_count", "buyer_funder_overlap_count", "ignored_shared_funder_count"):
        if result.get(field) is not None:
            try:
                result[field] = max(0, int(result[field]))
            except (TypeError, ValueError):
                result[field] = None
    result.setdefault("linkage_metric_origin", "missing")
    result.setdefault("linkage_status", "missing")
    result.setdefault("linkage_warning", None)
    return result
