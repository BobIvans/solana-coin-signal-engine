from __future__ import annotations

from typing import Any


def compute_wallet_netflow_bias(wallet_events: list[dict[str, Any]]) -> float:
    buys = sum(1 for event in wallet_events if str(event.get("side") or "buy").lower() == "buy")
    sells = sum(1 for event in wallet_events if str(event.get("side") or "").lower() == "sell")
    total = buys + sells
    if total == 0:
        return 0.0
    return round((buys - sells) / total, 4)


def count_early_wallet_entries(wallet_events: list[dict[str, Any]], early_window_sec: int) -> int:
    return sum(1 for event in wallet_events if int(event.get("age_sec") or 10**9) <= int(early_window_sec))


def compute_wallet_features(token_context: dict[str, Any], registry: dict[str, dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    events = list(token_context.get("wallet_events") or [])
    matched = [event for event in events if str(event.get("wallet_address") or "").lower() in registry]
    unique_wallets = {str(event.get("wallet_address") or "").lower() for event in matched}

    tier_weights = {
        "tier_1": float(config.get("tiers", {}).get("tier_1_weight", 1.0)),
        "tier_2": float(config.get("tiers", {}).get("tier_2_weight", 0.6)),
        "tier_3": float(config.get("tiers", {}).get("tier_3_weight", 0.25)),
    }

    score_sum = 0.0
    tier1 = 0
    tier2 = 0
    for wallet in unique_wallets:
        item = registry.get(wallet, {})
        tier = str(item.get("tier") or "tier_3")
        score_sum += float(item.get("score") or 0.0) * tier_weights.get(tier, 0.25)
        if tier == "tier_1":
            tier1 += 1
        if tier == "tier_2":
            tier2 += 1

    return {
        "smart_wallet_hits": len(matched),
        "smart_wallet_score_sum": round(score_sum, 4),
        "smart_wallet_tier1_hits": tier1,
        "smart_wallet_tier2_hits": tier2,
        "smart_wallet_unique_count": len(unique_wallets),
        "smart_wallet_early_entry_hits": count_early_wallet_entries(matched, int(config.get("features", {}).get("early_entry_window_sec", 120))),
        "smart_wallet_netflow_bias": compute_wallet_netflow_bias(matched),
    }
