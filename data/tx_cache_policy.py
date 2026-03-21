"""Freshness and stale-fallback policy for transaction lake batches."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data.tx_normalizer import TX_BATCH_CONTRACT_VERSION


def _coerce_epoch(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        epoch = int(value)
        return epoch if epoch >= 0 else None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        epoch = int(text)
        return epoch if epoch >= 0 else None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp())


def classify_tx_batch_freshness(
    tx_batch: dict[str, Any] | None,
    *,
    now_ts: int | None = None,
    max_age_sec: int = 900,
    stale_age_sec: int = 86_400,
) -> dict[str, Any]:
    now_ts = now_ts if now_ts is not None else int(datetime.now(timezone.utc).timestamp())
    if not isinstance(tx_batch, dict):
        return {"freshness": "missing", "age_sec": None, "reason": "tx_batch_missing"}

    batch_status = str(tx_batch.get("tx_batch_status") or tx_batch.get("batch_status") or "missing")
    if batch_status in {"missing", "malformed"}:
        return {"freshness": batch_status, "age_sec": None, "reason": f"batch_status:{batch_status}"}

    contract_version = str(tx_batch.get("contract_version") or "").strip()
    if contract_version and contract_version != TX_BATCH_CONTRACT_VERSION:
        return {
            "freshness": "refresh_required",
            "age_sec": None,
            "reason": "contract_version_mismatch",
            "expected_contract_version": TX_BATCH_CONTRACT_VERSION,
            "actual_contract_version": contract_version,
        }

    fetched_at = _coerce_epoch(
        tx_batch.get("tx_batch_fetched_at")
        or tx_batch.get("fetched_at")
        or tx_batch.get("tx_batch_normalized_at")
        or tx_batch.get("normalized_at")
    )
    if fetched_at is None:
        return {"freshness": "unknown", "age_sec": None, "reason": "fetched_at_missing"}

    age_sec = max(0, now_ts - fetched_at)
    if age_sec <= max(0, int(max_age_sec)):
        return {"freshness": "fresh_cache", "age_sec": age_sec, "reason": "within_ttl"}
    if age_sec <= max(0, int(stale_age_sec)):
        return {"freshness": "stale_cache_allowed", "age_sec": age_sec, "reason": "within_stale_ttl"}
    return {"freshness": "refresh_required", "age_sec": age_sec, "reason": "stale_ttl_exceeded"}


def should_refresh_tx_batch(
    tx_batch: dict[str, Any] | None,
    *,
    now_ts: int | None = None,
    max_age_sec: int = 900,
    allow_stale: bool = True,
    stale_age_sec: int = 86_400,
) -> bool:
    freshness = classify_tx_batch_freshness(
        tx_batch,
        now_ts=now_ts,
        max_age_sec=max_age_sec,
        stale_age_sec=stale_age_sec,
    )
    if freshness["freshness"] == "fresh_cache":
        return False
    if freshness["freshness"] == "stale_cache_allowed" and allow_stale:
        return False
    return True


def resolve_tx_fetch_mode(
    tx_batch: dict[str, Any] | None,
    *,
    upstream_failed: bool = False,
    now_ts: int | None = None,
    max_age_sec: int = 900,
    allow_stale: bool = True,
    stale_age_sec: int = 86_400,
) -> str:
    freshness = classify_tx_batch_freshness(
        tx_batch,
        now_ts=now_ts,
        max_age_sec=max_age_sec,
        stale_age_sec=stale_age_sec,
    )
    label = freshness["freshness"]
    if label == "fresh_cache":
        return "fresh_cache"
    if label == "stale_cache_allowed":
        if upstream_failed and allow_stale:
            return "upstream_failed_use_stale"
        return "stale_cache_allowed" if allow_stale else "refresh_required"
    if label == "refresh_required":
        if freshness.get("reason") == "contract_version_mismatch":
            return "refresh_required"
        if upstream_failed and allow_stale and isinstance(tx_batch, dict) and (tx_batch.get("record_count") or tx_batch.get("tx_batch_record_count")):
            return "upstream_failed_use_stale"
        return "refresh_required"
    if label in {"unknown", "partial"}:
        if upstream_failed and allow_stale and isinstance(tx_batch, dict):
            return "upstream_failed_use_stale"
        return "stale_cache_allowed" if allow_stale else "refresh_required"
    return "missing"


__all__ = [
    "classify_tx_batch_freshness",
    "resolve_tx_fetch_mode",
    "should_refresh_tx_batch",
]
