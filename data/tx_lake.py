"""Deterministic local transaction lake storage helpers."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
import hashlib
from datetime import datetime, timezone
DEFAULT_TX_LAKE_DIR = Path("data/cache/tx_batches")
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def _slugify(value: str, *, limit: int = 48) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    text = re.sub(r"-+", "-", text).strip("-._")
    return (text or "lookup")[:limit]
def _digest(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
def resolve_tx_lake_path(
    *,
    lookup_key: str,
    lookup_type: str,
    provider: str,
    root_dir: str | Path | None = None,
    window_bucket: str | None = None,
) -> Path:
    root = Path(root_dir) if root_dir is not None else DEFAULT_TX_LAKE_DIR
    provider_slug = _slugify(provider or "unknown")
    lookup_type_slug = _slugify(lookup_type or "unknown")
    lookup_slug = _slugify(lookup_key or "missing")
    digest = _digest(lookup_key or "missing")
    bucket = window_bucket or digest[:2]
    return root / provider_slug / lookup_type_slug / bucket / f"{lookup_slug}__{digest}.json"
def make_tx_lake_event(event: str, **payload: Any) -> dict[str, Any]:
    return {
        "ts": utc_now_iso(),
        "event": event,
        **{key: value for key, value in payload.items() if value not in (None, "", [], {})},
    }
def write_tx_batch(
    tx_batch: dict[str, Any],
    *,
    root_dir: str | Path | None = None,
    provider: str | None = None,
    lookup_key: str | None = None,
    lookup_type: str | None = None,
) -> Path:
    if not isinstance(tx_batch, dict):
        raise TypeError("tx_batch must be a dict")
    resolved_provider = provider or str(tx_batch.get("source_provider") or "unknown")
    resolved_lookup_key = lookup_key or str(tx_batch.get("lookup_key") or tx_batch.get("tx_batch_lookup_key") or "missing")
    resolved_lookup_type = lookup_type or str(tx_batch.get("lookup_type") or "unknown")
    path = resolve_tx_lake_path(
        lookup_key=resolved_lookup_key,
        lookup_type=resolved_lookup_type,
        provider=resolved_provider,
        root_dir=root_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tx_batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
def load_tx_batch(
    *,
    lookup_key: str | None = None,
    lookup_type: str | None = None,
    provider: str | None = None,
    root_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    target = Path(path) if path is not None else resolve_tx_lake_path(
        lookup_key=str(lookup_key or "missing"),
        lookup_type=str(lookup_type or "unknown"),
        provider=str(provider or "unknown"),
        root_dir=root_dir,
    )
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "lookup_key": lookup_key,
            "lookup_type": lookup_type,
            "source_provider": provider,
            "tx_batch_status": "malformed",
            "tx_batch_warning": "failed_to_parse_tx_batch",
            "tx_records": [],
            "record_count": 0,
            "tx_batch_record_count": 0,
            "tx_batch_path": str(target),
        }
    if isinstance(payload, dict):
        payload.setdefault("tx_batch_path", str(target))
        return payload
    return {
        "lookup_key": lookup_key,
        "lookup_type": lookup_type,
        "source_provider": provider,
        "tx_batch_status": "malformed",
        "tx_batch_warning": "tx_batch_not_object",
        "tx_records": [],
        "record_count": 0,
        "tx_batch_record_count": 0,
        "tx_batch_path": str(target),
    }
def get_tx_lake_status(
    *,
    lookup_key: str,
    lookup_type: str,
    provider: str,
    root_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_tx_lake_path(
        lookup_key=lookup_key,
        lookup_type=lookup_type,
        provider=provider,
        root_dir=root_dir,
    )
    payload = load_tx_batch(path=path)
    if payload is None:
        return {
            "lookup_key": lookup_key,
            "lookup_type": lookup_type,
            "source_provider": provider,
            "path": str(path),
            "tx_batch_status": "missing",
            "tx_batch_record_count": 0,
        }
    return {
        "lookup_key": str(payload.get("lookup_key") or payload.get("tx_batch_lookup_key") or lookup_key),
        "lookup_type": str(payload.get("lookup_type") or lookup_type),
        "source_provider": str(payload.get("source_provider") or provider),
        "path": str(path),
        "tx_batch_status": str(payload.get("tx_batch_status") or payload.get("batch_status") or "missing"),
        "tx_batch_freshness": payload.get("tx_batch_freshness") or payload.get("freshness_status"),
        "tx_batch_warning": payload.get("tx_batch_warning"),
        "tx_batch_record_count": int(payload.get("tx_batch_record_count") or payload.get("record_count") or 0),
        "tx_batch_fetched_at": payload.get("tx_batch_fetched_at") or payload.get("fetched_at"),
        "tx_batch_normalized_at": payload.get("tx_batch_normalized_at") or payload.get("normalized_at"),
        "contract_version": payload.get("contract_version"),
    }
def list_tx_lake_batches(
    *,
    root_dir: str | Path | None = None,
    provider: str | None = None,
    lookup_type: str | None = None,
) -> list[dict[str, Any]]:
    root = Path(root_dir) if root_dir is not None else DEFAULT_TX_LAKE_DIR
    base = root
    if provider:
        base = base / _slugify(provider)
    if lookup_type:
        base = base / _slugify(lookup_type)
    if not base.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        payload = load_tx_batch(path=path)
        if not isinstance(payload, dict):
            continue
        summaries.append(
            {
                "path": str(path),
                "lookup_key": payload.get("lookup_key") or payload.get("tx_batch_lookup_key"),
                "lookup_type": payload.get("lookup_type"),
                "source_provider": payload.get("source_provider"),
                "tx_batch_status": payload.get("tx_batch_status") or payload.get("batch_status"),
                "tx_batch_freshness": payload.get("tx_batch_freshness") or payload.get("freshness_status"),
                "tx_batch_record_count": int(payload.get("tx_batch_record_count") or payload.get("record_count") or 0),
                "contract_version": payload.get("contract_version"),
            }
        )
    return summaries
__all__ = [
    "DEFAULT_TX_LAKE_DIR",
    "get_tx_lake_status",
    "list_tx_lake_batches",
    "load_tx_batch",
    "make_tx_lake_event",
    "resolve_tx_lake_path",
    "write_tx_batch",
]
