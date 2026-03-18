"""Wallet-registry-aware enrichment helpers layered over raw smart-wallet hits."""

from __future__ import annotations

from typing import Any

from collectors.wallet_registry_loader import (
    WALLET_REGISTRY_STATUS_EMPTY,
    WALLET_REGISTRY_STATUS_MISSING,
    WALLET_REGISTRY_STATUS_VALIDATED,
)

ACTIVE_TIER_WEIGHTS: dict[str, float] = {
    "tier_1": 1.00,
    "tier_2": 0.60,
    "tier_3": 0.30,
}
WATCH_WEIGHT = 0.10
CONVICTION_BONUS_CAP = 0.75
HOT_TIER_BONUS: dict[str, float] = {
    "tier_1": 0.35,
    "tier_2": 0.20,
    "tier_3": 0.10,
}



def _normalize_wallets(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return sorted({str(value or "").strip() for value in (values or []) if str(value or "").strip()})



def _score_for_record(record: dict[str, Any]) -> float:
    status = str(record.get("status") or "watch")
    tier = str(record.get("tier") or "tier_3")
    if status == "active":
        return ACTIVE_TIER_WEIGHTS.get(tier, 0.0)
    if status in {"watch", "watch_pending_validation"}:
        return WATCH_WEIGHT
    return 0.0



def _conviction_bonus_for_record(record: dict[str, Any]) -> float:
    if not bool(record.get("is_hot")) or str(record.get("status") or "") != "active":
        return 0.0
    return HOT_TIER_BONUS.get(str(record.get("tier") or "tier_3"), 0.0)



def _confidence_for_hits(*, active_tier12_hits: int, active_hits: int, watch_hits: int) -> str:
    if active_tier12_hits >= 2:
        return "high"
    if active_hits >= 1 or watch_hits >= 2:
        return "medium"
    return "low"



def default_wallet_registry_bias(
    *,
    wallet_registry_status: str,
    wallet_registry_hot_set_size: int,
    wallet_registry_validated_size: int,
) -> dict[str, Any]:
    return {
        "wallet_registry_status": wallet_registry_status,
        "wallet_registry_hot_set_size": int(wallet_registry_hot_set_size or 0),
        "wallet_registry_validated_size": int(wallet_registry_validated_size or 0),
        "smart_wallet_score_sum": 0.0,
        "smart_wallet_tier1_hits": 0,
        "smart_wallet_tier2_hits": 0,
        "smart_wallet_tier3_hits": 0,
        "smart_wallet_early_entry_hits": 0,
        "smart_wallet_active_hits": 0,
        "smart_wallet_watch_hits": 0,
        "smart_wallet_hit_tiers": [],
        "smart_wallet_hit_statuses": [],
        "smart_wallet_netflow_bias": None,
        "smart_wallet_conviction_bonus": 0.0,
        "smart_wallet_registry_confidence": "low",
    }



def compute_wallet_registry_bias(raw_hit_wallets: list[str] | tuple[str, ...] | None, lookup: dict[str, Any]) -> dict[str, Any]:
    status = str(lookup.get("status") or WALLET_REGISTRY_STATUS_MISSING)
    hot_set_size = int(lookup.get("hot_set_size") or 0)
    validated_size = int(lookup.get("validated_size") or 0)
    defaults = default_wallet_registry_bias(
        wallet_registry_status=status,
        wallet_registry_hot_set_size=hot_set_size,
        wallet_registry_validated_size=validated_size,
    )
    if status in {WALLET_REGISTRY_STATUS_MISSING, WALLET_REGISTRY_STATUS_EMPTY}:
        return defaults
    if status != WALLET_REGISTRY_STATUS_VALIDATED:
        return defaults

    registry = lookup.get("validated_wallets") or {}
    matched_records = [registry[wallet] for wallet in _normalize_wallets(raw_hit_wallets) if wallet in registry]
    if not matched_records:
        return defaults

    tier1_hits = sum(1 for record in matched_records if str(record.get("tier") or "") == "tier_1")
    tier2_hits = sum(1 for record in matched_records if str(record.get("tier") or "") == "tier_2")
    tier3_hits = sum(1 for record in matched_records if str(record.get("tier") or "") == "tier_3")
    active_hits = sum(1 for record in matched_records if str(record.get("status") or "") == "active")
    watch_hits = sum(1 for record in matched_records if str(record.get("status") or "").startswith("watch"))
    early_entry_hits = sum(1 for record in matched_records if bool(record.get("early_entry_positive")))
    score_sum = round(sum(_score_for_record(record) for record in matched_records), 6)
    conviction_bonus = round(
        min(CONVICTION_BONUS_CAP, sum(_conviction_bonus_for_record(record) for record in matched_records)),
        6,
    )
    confidence = _confidence_for_hits(
        active_tier12_hits=sum(
            1
            for record in matched_records
            if str(record.get("status") or "") == "active"
            and str(record.get("tier") or "") in {"tier_1", "tier_2"}
        ),
        active_hits=active_hits,
        watch_hits=watch_hits,
    )

    return {
        **defaults,
        "smart_wallet_score_sum": score_sum,
        "smart_wallet_tier1_hits": tier1_hits,
        "smart_wallet_tier2_hits": tier2_hits,
        "smart_wallet_tier3_hits": tier3_hits,
        "smart_wallet_early_entry_hits": early_entry_hits,
        "smart_wallet_active_hits": active_hits,
        "smart_wallet_watch_hits": watch_hits,
        "smart_wallet_hit_tiers": sorted({str(record.get("tier") or "") for record in matched_records if record.get("tier")}),
        "smart_wallet_hit_statuses": sorted({str(record.get("status") or "") for record in matched_records if record.get("status")}),
        "smart_wallet_conviction_bonus": conviction_bonus,
        "smart_wallet_registry_confidence": confidence,
    }


__all__ = [
    "ACTIVE_TIER_WEIGHTS",
    "CONVICTION_BONUS_CAP",
    "compute_wallet_registry_bias",
    "default_wallet_registry_bias",
]
