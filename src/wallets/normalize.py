from __future__ import annotations

import re
from typing import Any

from src.wallets.types import VALID_STATUSES, VALID_TIERS

_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def validate_wallet_address(address: Any) -> bool:
    if address is None:
        return False
    value = str(address).strip()
    return bool(_ADDRESS_RE.fullmatch(value))


def normalize_tier(value: Any) -> str:
    normalized = str(value or "tier_3").strip().lower().replace("-", "_")
    if normalized in {"tier1", "t1"}:
        normalized = "tier_1"
    if normalized in {"tier2", "t2"}:
        normalized = "tier_2"
    if normalized in {"tier3", "t3"}:
        normalized = "tier_3"
    return normalized if normalized in VALID_TIERS else "tier_3"


def normalize_status(value: Any) -> str:
    normalized = str(value or "active").strip().lower()
    return normalized if normalized in VALID_STATUSES else "active"


def normalize_wallet_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_address = str(record.get("wallet_address") or "").strip()
    normalized = {
        "wallet_address": raw_address,
        "source": str(record.get("source") or "unknown").strip() or "unknown",
        "tier": normalize_tier(record.get("tier")),
        "score": max(0.0, min(1.0, float(record.get("score") or 0.0))),
        "notes": str(record.get("notes") or "").strip(),
        "first_seen_at": str(record.get("first_seen_at") or "").strip(),
        "last_seen_at": str(record.get("last_seen_at") or "").strip(),
        "status": normalize_status(record.get("status")),
    }
    normalized["wallet_address"] = normalized["wallet_address"].lower()
    if not validate_wallet_address(raw_address):
        normalized["_invalid_reason"] = "invalid_wallet_address"
    return normalized
