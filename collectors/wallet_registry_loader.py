"""Load and normalize deterministic wallet registry inputs from PR-SW-1/SW-3 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.wallet_seed_import import is_plausible_solana_wallet
from utils.io import read_json

NORMALIZED_CONTRACT_VERSION = "wallet_seed_import.v1"
WALLET_REGISTRY_STATUS_VALIDATED = "validated"
WALLET_REGISTRY_STATUS_MISSING = "degraded_missing_registry"
WALLET_REGISTRY_STATUS_EMPTY = "degraded_empty_registry"


VALIDATED_TIER_KEYS = ("new_tier", "tier")
VALIDATED_STATUS_KEYS = ("new_status", "status")
EARLY_ENTRY_TAGS = {"early_entry_positive", "early_entry", "early_entry_winner"}


def _normalize_string_list(values: Any) -> list[str]:
    out = {str(value or "").strip() for value in (values or []) if str(value or "").strip()}
    return sorted(out)



def _normalize_notes(value: Any) -> str:
    return str(value or "").strip()



def _derive_source_names(candidate: dict[str, Any]) -> list[str]:
    if candidate.get("source_names"):
        return _normalize_string_list(candidate.get("source_names"))
    source_records = candidate.get("source_records") or []
    names = [record.get("source_name") for record in source_records if isinstance(record, dict)]
    return _normalize_string_list(names)



def _derive_tags(candidate: dict[str, Any]) -> list[str]:
    tags = candidate.get("tags")
    if isinstance(tags, list):
        return _normalize_string_list(tags)
    tag = str(candidate.get("tag") or "").strip().lower()
    return [tag] if tag else []



def _merge_duplicate(into_record: dict[str, Any], duplicate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(into_record)
    merged["source_names"] = sorted(set(into_record["source_names"]) | set(duplicate["source_names"]))
    merged["source_count"] = len(merged["source_names"])
    merged["tags"] = sorted(set(into_record["tags"]) | set(duplicate["tags"]))
    merged["notes"] = into_record["notes"] or duplicate["notes"]
    merged["manual_priority"] = bool(into_record["manual_priority"] or duplicate["manual_priority"])
    merged["source_records"] = sorted(
        list(into_record["source_records"]) + list(duplicate["source_records"]),
        key=lambda item: (
            str(item.get("file_path") or ""),
            str(item.get("source_type") or ""),
            str(item.get("observed_at") or ""),
        ),
    )
    merged["quality_flags"] = dict(merged.get("quality_flags", {}))
    merged["quality_flags"]["duplicate_source_merged"] = True
    return merged



def load_normalized_wallet_candidates(path: str | Path) -> dict[str, Any]:
    payload = read_json(path, default={}) or {}
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("normalized_wallet_candidates artifact missing candidates[]")

    deduped: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()

    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        wallet = str(raw.get("wallet") or "").strip()
        source_names = _derive_source_names(raw)
        source_records = raw.get("source_records") if isinstance(raw.get("source_records"), list) else []
        record = {
            "wallet": wallet,
            "source_names": source_names,
            "source_count": max(int(raw.get("source_count") or len(source_names) or 0), len(source_names)),
            "manual_priority": bool(raw.get("manual_priority", False)),
            "tags": _derive_tags(raw),
            "notes": _normalize_notes(raw.get("notes")),
            "source_records": source_records,
            "imported_at": str(raw.get("imported_at") or payload.get("generated_at") or ""),
            "input_status": str(raw.get("status") or "candidate"),
            "format_confidence": 1.0 if is_plausible_solana_wallet(wallet) else 0.0,
            "wallet_cluster_id": raw.get("wallet_cluster_id") or raw.get("cluster_id"),
            "funder": raw.get("funder") or raw.get("funding_source") or raw.get("funded_by"),
            "launch_group": raw.get("launch_group") or raw.get("launch_id") or raw.get("group_key"),
            "wallet_family_hint": raw.get("wallet_family_hint") or raw.get("family_hint") or raw.get("registry_family_hint"),
            "independent_family_hint": raw.get("independent_family_hint") or raw.get("wallet_independent_family_hint"),
            "linkage_group": raw.get("linkage_group") or raw.get("linkage_hint"),
            "linked_wallets": raw.get("linked_wallets") or raw.get("wallet_family_peers") or [],
            "creator_linked": bool(raw.get("creator_linked") or raw.get("creator_overlap") or raw.get("dev_linked")),
            "quality_flags": {
                "invalid_format_rejected": not is_plausible_solana_wallet(wallet),
                "duplicate_source_merged": False,
                "manual_seed": bool(raw.get("manual_priority", False)),
                "sparse_metadata": not bool(_derive_tags(raw)) and not bool(_normalize_notes(raw.get("notes"))),
                "requires_replay_validation": True,
            },
        }
        if wallet in deduped:
            duplicates.add(wallet)
            deduped[wallet] = _merge_duplicate(deduped[wallet], record)
            continue
        deduped[wallet] = record

    ordered = [deduped[wallet] for wallet in sorted(deduped)]
    for record in ordered:
        if record["wallet"] in duplicates:
            record["quality_flags"]["duplicate_source_merged"] = True

    return {
        "contract_version": payload.get("contract_version", NORMALIZED_CONTRACT_VERSION),
        "generated_at": payload.get("generated_at") or "",
        "input_summary": payload.get("input_summary") or {},
        "candidates": ordered,
    }



def _path_exists(path: str | Path | None) -> bool:
    return bool(path) and Path(path).expanduser().resolve().exists()



def _first_present(record: dict[str, Any], keys: tuple[str, ...], default: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return default



def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False



def _has_early_entry_positive(record: dict[str, Any]) -> bool:
    tags = {str(tag or "").strip().lower() for tag in (record.get("tags") or []) if str(tag or "").strip()}
    replay_evidence = record.get("replay_evidence") if isinstance(record.get("replay_evidence"), dict) else {}
    if tags & EARLY_ENTRY_TAGS:
        return True
    return any(
        _truthy(record.get(key)) or _truthy(replay_evidence.get(key))
        for key in ("early_entry_positive", "early_entry_winner", "early_entry_flag")
    )



def _normalize_validated_wallet_record(record: dict[str, Any], *, is_hot: bool) -> dict[str, Any] | None:
    wallet = str(record.get("wallet") or record.get("wallet_address") or "").strip()
    if not wallet:
        return None
    tier = _first_present(record, VALIDATED_TIER_KEYS, "tier_3")
    status = _first_present(record, VALIDATED_STATUS_KEYS, "watch")
    replay_evidence = record.get("replay_evidence") if isinstance(record.get("replay_evidence"), dict) else {}
    return {
        "wallet": wallet,
        "tier": tier,
        "status": status,
        "registry_score": float(record.get("registry_score") or 0.0),
        "tags": _normalize_string_list(record.get("tags") or []),
        "notes": _normalize_notes(record.get("notes")),
        "is_hot": bool(is_hot),
        "early_entry_positive": _has_early_entry_positive(record),
        "replay_evidence": replay_evidence,
        "wallet_family_id": record.get("wallet_family_id"),
        "independent_family_id": record.get("independent_family_id"),
        "wallet_family_confidence": float(record.get("wallet_family_confidence") or 0.0),
        "wallet_family_origin": str(record.get("wallet_family_origin") or "missing"),
        "wallet_family_reason_codes": _normalize_string_list(record.get("wallet_family_reason_codes") or []),
        "wallet_cluster_id": record.get("wallet_cluster_id"),
        "wallet_family_member_count": int(record.get("wallet_family_member_count") or 0),
        "wallet_family_shared_funder_flag": bool(record.get("wallet_family_shared_funder_flag", False)),
        "wallet_family_creator_link_flag": bool(record.get("wallet_family_creator_link_flag", False)),
        "wallet_family_status": str(record.get("wallet_family_status") or "missing"),
    }



def _wallet_mapping(payload: dict[str, Any] | None, *, hot_wallets: set[str] | None = None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    hot_wallets = hot_wallets or set()
    wallets = payload.get("wallets") if isinstance(payload, dict) else []
    if not isinstance(wallets, list):
        return out
    for raw in wallets:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_validated_wallet_record(raw, is_hot=str(raw.get("wallet") or "") in hot_wallets)
        if not normalized:
            continue
        out[normalized["wallet"]] = normalized
    return out



def load_wallet_registry_lookup(
    validated_registry_path: str | Path | None,
    hot_registry_path: str | Path | None,
) -> dict[str, Any]:
    resolved_validated = Path(validated_registry_path).expanduser().resolve() if validated_registry_path else None
    resolved_hot = Path(hot_registry_path).expanduser().resolve() if hot_registry_path else None

    if resolved_validated is None or not _path_exists(resolved_validated):
        return {
            "status": WALLET_REGISTRY_STATUS_MISSING,
            "validated_size": 0,
            "hot_set_size": 0,
            "validated_wallets": {},
            "hot_wallets": set(),
            "validated_registry_path": str(resolved_validated) if resolved_validated else "",
            "hot_registry_path": str(resolved_hot) if resolved_hot else "",
        }

    validated_payload = read_json(resolved_validated, default={}) or {}
    hot_payload = read_json(resolved_hot, default={}) if resolved_hot and _path_exists(resolved_hot) else {}
    hot_rows = hot_payload.get("wallets") if isinstance(hot_payload, dict) else []
    hot_wallets = {
        str(item.get("wallet") or item.get("wallet_address") or "").strip()
        for item in (hot_rows or [])
        if isinstance(item, dict) and str(item.get("wallet") or item.get("wallet_address") or "").strip()
    }
    normalized = _wallet_mapping(validated_payload, hot_wallets=hot_wallets)
    if not normalized:
        return {
            "status": WALLET_REGISTRY_STATUS_EMPTY,
            "validated_size": 0,
            "hot_set_size": 0,
            "validated_wallets": {},
            "hot_wallets": set(),
            "validated_registry_path": str(resolved_validated),
            "hot_registry_path": str(resolved_hot) if resolved_hot else "",
            "contract_version": validated_payload.get("contract_version") or "",
        }

    return {
        "status": WALLET_REGISTRY_STATUS_VALIDATED,
        "validated_size": len(normalized),
        "hot_set_size": len(hot_wallets),
        "validated_wallets": normalized,
        "hot_wallets": hot_wallets,
        "validated_registry_path": str(resolved_validated),
        "hot_registry_path": str(resolved_hot) if resolved_hot else "",
        "contract_version": validated_payload.get("contract_version") or "",
        "hot_contract_version": hot_payload.get("contract_version") if isinstance(hot_payload, dict) else "",
    }


__all__ = [
    "NORMALIZED_CONTRACT_VERSION",
    "WALLET_REGISTRY_STATUS_EMPTY",
    "WALLET_REGISTRY_STATUS_MISSING",
    "WALLET_REGISTRY_STATUS_VALIDATED",
    "load_normalized_wallet_candidates",
    "load_wallet_registry_lookup",
]
