"""Load and normalize deterministic wallet registry inputs from PR-SW-1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.wallet_seed_import import is_plausible_solana_wallet
from utils.io import read_json

NORMALIZED_CONTRACT_VERSION = "wallet_seed_import.v1"


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


__all__ = ["NORMALIZED_CONTRACT_VERSION", "load_normalized_wallet_candidates"]
