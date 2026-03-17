from __future__ import annotations

from dataclasses import dataclass


VALID_TIERS = {"tier_1", "tier_2", "tier_3"}
VALID_STATUSES = {"active", "inactive", "quarantine"}


@dataclass(frozen=True)
class WalletRecord:
    wallet_address: str
    source: str
    tier: str
    score: float
    notes: str
    first_seen_at: str
    last_seen_at: str
    status: str
