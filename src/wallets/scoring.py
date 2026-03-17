from __future__ import annotations

from typing import Any


def compute_wallet_score_adjustment(wallet_features: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    scoring = config.get("scoring", {})
    bonus = 0.0
    penalty = 0.0
    reasons: list[str] = []

    if int(wallet_features.get("smart_wallet_tier1_hits") or 0) >= 1:
        bonus += float(scoring.get("tier1_bonus_score", 3.0))
        reasons.append("tier1_wallet_bonus")
    if int(wallet_features.get("smart_wallet_tier2_hits") or 0) >= 1:
        bonus += float(scoring.get("tier2_bonus_score", 1.0))
        reasons.append("tier2_wallet_bonus")
    if int(wallet_features.get("smart_wallet_early_entry_hits") or 0) >= 1:
        bonus += float(scoring.get("early_entry_bonus_score", 2.0))
        reasons.append("early_wallet_bonus")
    if float(wallet_features.get("smart_wallet_netflow_bias") or 0.0) < 0:
        penalty += float(scoring.get("negative_netflow_penalty", 3.0))
        reasons.append("negative_wallet_netflow_penalty")

    bonus = min(bonus, float(scoring.get("max_wallet_bonus_score", 6.0)))
    return {"wallet_bonus_score": round(bonus, 4), "wallet_penalty_score": round(penalty, 4), "reason_codes": reasons}


def apply_wallet_adjustment_to_final_score(base_score: float, wallet_adjustment: dict[str, Any], config: dict[str, Any]) -> float:
    _ = config
    return round(float(base_score) + float(wallet_adjustment.get("wallet_bonus_score") or 0.0) - float(wallet_adjustment.get("wallet_penalty_score") or 0.0), 4)
