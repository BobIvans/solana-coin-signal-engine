"""Normalization helpers for deterministic transaction lake batches."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

TX_BATCH_CONTRACT_VERSION = "tx_batch.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "success", "confirmed"}:
        return True
    if text in {"false", "0", "no", "n", "failed", "error"}:
        return False
    return None


def _coerce_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _coerce_iso_or_ts(value: Any) -> int | None:
    integer = _coerce_int(value)
    if integer is not None:
        return integer if integer > 0 else None
    text = _coerce_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    ts = int(parsed.timestamp())
    return ts if ts > 0 else None


def _stable_digest(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return None


def _normalize_transfer(transfer: Any, transfer_type: str) -> dict[str, Any] | None:
    if not isinstance(transfer, dict):
        return None
    amount = _coerce_float(_first_present(transfer, ("amount", "tokenAmount", "uiAmount", "amount_ui", "lamports")))
    decimals = _coerce_int(_first_present(transfer, ("decimals",)))
    return {
        "transfer_type": transfer_type,
        "from_user_account": _coerce_text(_first_present(transfer, ("fromUserAccount", "from_user_account", "source", "from"))),
        "to_user_account": _coerce_text(_first_present(transfer, ("toUserAccount", "to_user_account", "destination", "to"))),
        "user_account": _coerce_text(_first_present(transfer, ("userAccount", "user_account", "owner"))),
        "mint": _coerce_text(_first_present(transfer, ("mint", "tokenAddress", "token_address"))),
        "amount": amount,
        "decimals": decimals,
        "raw": transfer,
    }


def _normalize_native_transfers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("nativeTransfers") or payload.get("native_transfers") or []
    if not isinstance(value, list):
        return []
    return [item for item in (_normalize_transfer(transfer, "native") for transfer in value) if item is not None]


def _normalize_token_transfers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("tokenTransfers") or payload.get("token_transfers") or []
    if not isinstance(value, list):
        return []
    return [item for item in (_normalize_transfer(transfer, "token") for transfer in value) if item is not None]


def _normalize_signers(payload: dict[str, Any]) -> list[str]:
    signers: list[str] = []
    raw = payload.get("signers")
    if isinstance(raw, list):
        for item in raw:
            text = _coerce_text(item)
            if text and text not in signers:
                signers.append(text)
    signer = _coerce_text(_first_present(payload, ("signer", "feePayer", "fee_payer", "owner", "user")))
    if signer and signer not in signers:
        signers.append(signer)
    return signers


def normalize_tx_record(
    raw_record: dict[str, Any],
    *,
    source_provider: str,
    lookup_key: str,
    lookup_type: str,
    record_index: int = 0,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    if not isinstance(raw_record, dict):
        return None, ["raw_record_not_dict"]

    signature = _coerce_text(
        _first_present(raw_record, ("signature", "tx_signature", "id", "hash"))
    )
    timestamp = _coerce_iso_or_ts(_first_present(raw_record, ("timestamp", "blockTime", "block_time", "time", "seen_at")))
    slot = _coerce_int(_first_present(raw_record, ("slot", "block", "block_slot", "block_number")))

    if not signature:
        synthetic = _stable_digest({"lookup_key": lookup_key, "record_index": record_index, "raw": raw_record})
        signature = f"synthetic:{synthetic}"
        warnings.append("signature_missing_synthesized")
    if timestamp is None:
        warnings.append("timestamp_missing")
    if slot is None:
        warnings.append("slot_missing")

    token_transfers = _normalize_token_transfers(raw_record)
    native_transfers = _normalize_native_transfers(raw_record)
    signers = _normalize_signers(raw_record)

    success = _coerce_bool(_first_present(raw_record, ("success", "isSuccess", "status_ok")))
    if success is None:
        err = raw_record.get("err")
        tx_error = raw_record.get("transactionError")
        if err not in (None, "", False) or tx_error not in (None, "", False):
            success = False
        elif "success" in raw_record or "isSuccess" in raw_record or "transactionError" in raw_record or "err" in raw_record:
            success = True

    batch_status = "usable"
    if warnings:
        batch_status = "partial"

    record = {
        "signature": signature,
        "token_address": _coerce_text(_first_present(raw_record, ("token_address", "tokenAddress", "mint"))) or (lookup_key if lookup_type == "token_address" else None),
        "pair_address": _coerce_text(_first_present(raw_record, ("pair_address", "pairAddress"))) or (lookup_key if lookup_type == "pair_address" else None),
        "source_address": _coerce_text(_first_present(raw_record, ("source_address", "address", "account"))) or (lookup_key if lookup_type in {"address", "source_address"} else None),
        "timestamp": timestamp,
        "block_time": timestamp,
        "blockTime": timestamp,
        "slot": slot,
        "block": slot,
        "raw_provider_source": source_provider,
        "source_provider": source_provider,
        "success": success,
        "status": _coerce_text(_first_present(raw_record, ("status", "result", "outcome"))),
        "fee_payer": _coerce_text(_first_present(raw_record, ("feePayer", "fee_payer"))),
        "feePayer": _coerce_text(_first_present(raw_record, ("feePayer", "fee_payer"))),
        "signers": signers,
        "signer": signers[0] if signers else None,
        "token_transfers": token_transfers,
        "tokenTransfers": [transfer["raw"] for transfer in token_transfers],
        "native_transfers": native_transfers,
        "nativeTransfers": [transfer["raw"] for transfer in native_transfers],
        "liquidity_usd": _coerce_float(_first_present(raw_record, ("liquidity_usd", "liquidityUsd", "liquidity"))),
        "bundle_id": _coerce_text(_first_present(raw_record, ("bundle_id", "bundleId"))),
        "group_id": _coerce_text(_first_present(raw_record, ("group_id", "groupKey", "group_key"))),
        "lookup_key": lookup_key,
        "lookup_type": lookup_type,
        "record_status": batch_status,
        "provenance": {
            "source_provider": source_provider,
            "lookup_key": lookup_key,
            "lookup_type": lookup_type,
            "record_index": record_index,
            "raw_keys": sorted(raw_record.keys()),
        },
        "raw_record": raw_record,
    }
    return record, warnings


def _infer_batch_status(records: list[dict[str, Any]], warnings: list[str]) -> str:
    if not records:
        return "missing" if not warnings else "malformed"
    if warnings:
        return "partial"
    if all(not record.get("tokenTransfers") and not record.get("nativeTransfers") for record in records):
        return "partial"
    return "usable"


def normalize_tx_batch(
    raw_records: list[dict[str, Any]] | None,
    *,
    source_provider: str,
    lookup_key: str,
    lookup_type: str,
    fetched_at: str | None = None,
    normalized_at: str | None = None,
    tx_batch_origin: str = "upstream_fetch",
    tx_batch_freshness: str = "fresh_cache",
) -> dict[str, Any]:
    fetched_at = fetched_at or utc_now_iso()
    normalized_at = normalized_at or utc_now_iso()
    raw_records = raw_records if isinstance(raw_records, list) else []

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    malformed_count = 0
    for index, raw_record in enumerate(raw_records):
        normalized, record_warnings = normalize_tx_record(
            raw_record,
            source_provider=source_provider,
            lookup_key=lookup_key,
            lookup_type=lookup_type,
            record_index=index,
        )
        warnings.extend(record_warnings)
        if normalized is None:
            malformed_count += 1
            continue
        records.append(normalized)

    batch_status = _infer_batch_status(records, warnings)
    batch_warning = "; ".join(sorted(set(warnings))) if warnings else None
    normalization_status = "ok"
    if batch_status == "partial":
        normalization_status = "partial"
    elif batch_status in {"missing", "malformed"}:
        normalization_status = "malformed"

    return {
        "contract_version": TX_BATCH_CONTRACT_VERSION,
        "generated_at": normalized_at,
        "source_provider": source_provider,
        "lookup_key": lookup_key,
        "lookup_type": lookup_type,
        "fetched_at": fetched_at,
        "normalized_at": normalized_at,
        "freshness_status": tx_batch_freshness,
        "batch_status": batch_status,
        "normalization_status": normalization_status,
        "warnings": sorted(set(warnings)),
        "record_count": len(records),
        "tx_batch_origin": tx_batch_origin,
        "tx_batch_status": batch_status,
        "tx_batch_warning": batch_warning,
        "tx_batch_freshness": tx_batch_freshness,
        "tx_batch_fetched_at": fetched_at,
        "tx_batch_normalized_at": normalized_at,
        "tx_batch_lookup_key": lookup_key,
        "tx_batch_record_count": len(records),
        "malformed_record_count": malformed_count,
        "tx_records": records,
    }


__all__ = [
    "TX_BATCH_CONTRACT_VERSION",
    "normalize_tx_batch",
    "normalize_tx_record",
    "utc_now_iso",
]
