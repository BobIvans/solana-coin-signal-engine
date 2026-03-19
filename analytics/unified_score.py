"""Unified scoring orchestration across on-chain, X, and rug layers."""

from __future__ import annotations

from typing import Any

from analytics.score_components import (
    compute_bundle_aggression_bonus,
    compute_bundle_risk_penalties,
    compute_cluster_quality_adjustment,
    compute_confidence_adjustment,
    compute_early_signal_bonus,
    compute_onchain_core,
    compute_rug_penalty,
    compute_spam_penalty,
    compute_x_validation_bonus,
)
from analytics.score_router import route_score
from src.wallets.scoring import (
    apply_wallet_adjustment_to_final_score,
    compute_wallet_score_adjustment,
)
from utils.bundle_contract_fields import copy_bundle_contract_fields
from utils.clock import utc_now_iso
from utils.short_horizon_contract_fields import copy_short_horizon_contract_fields


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _status_block(token_ctx: dict) -> dict:
    return {
        "fast_prescore_present": token_ctx.get("fast_prescore") is not None,
        "x_present": token_ctx.get("x_validation_score") is not None,
        "enrichment_present": token_ctx.get("holder_growth_5m") is not None
        or token_ctx.get("top20_holder_share") is not None,
        "rug_present": token_ctx.get("rug_score") is not None,
        "x_status": str(token_ctx.get("x_status") or "missing"),
        "enrichment_status": str(token_ctx.get("enrichment_status") or "ok"),
        "rug_status": str(token_ctx.get("rug_status") or "ok"),
    }


def score_token(token_ctx: dict, settings: Any) -> dict:
    onchain = compute_onchain_core(token_ctx, settings)
    early = compute_early_signal_bonus(token_ctx, settings)
    bundle_bonus = compute_bundle_aggression_bonus(token_ctx, settings)
    cluster_adjustment = compute_cluster_quality_adjustment(token_ctx, settings)
    bundle_risk = compute_bundle_risk_penalties(token_ctx, settings)
    x_bonus = compute_x_validation_bonus(token_ctx, settings)
    rug = compute_rug_penalty(token_ctx, settings)
    spam = compute_spam_penalty(token_ctx, settings)
    conf = compute_confidence_adjustment(token_ctx, settings)

    confidence_adjustment = float(conf.get("confidence_adjustment") or 0.0) + float(
        x_bonus.get("confidence_adjustment") or 0.0
    )

    base_score = _clamp(
        float(onchain["onchain_core"])
        + float(early["early_signal_bonus"])
        + float(bundle_bonus["bundle_aggression_bonus"])
        + float(cluster_adjustment["organic_multi_cluster_bonus"])
        + float(x_bonus["x_validation_bonus"])
        - float(cluster_adjustment["single_cluster_penalty"])
        - float(cluster_adjustment["creator_cluster_penalty"])
        - float(bundle_risk["bundle_sell_heavy_penalty"])
        - float(bundle_risk["retry_manipulation_penalty"])
        - float(rug["rug_penalty"])
        - float(spam["spam_penalty"])
        + confidence_adjustment
    )

    wallet_adjustment = compute_wallet_score_adjustment(
        token_ctx.get("wallet_features") or {},
        {
            "scoring": {
                "tier1_bonus_score": getattr(settings, "WALLET_TIER1_BONUS_SCORE", 3.0),
                "tier2_bonus_score": getattr(settings, "WALLET_TIER2_BONUS_SCORE", 1.0),
                "early_entry_bonus_score": getattr(
                    settings, "WALLET_EARLY_ENTRY_BONUS_SCORE", 2.0
                ),
                "negative_netflow_penalty": getattr(
                    settings, "WALLET_NEGATIVE_NETFLOW_PENALTY", 3.0
                ),
                "max_wallet_bonus_score": getattr(
                    settings, "WALLET_MAX_BONUS_SCORE", 6.0
                ),
            }
        },
    )
    final_score = _clamp(
        apply_wallet_adjustment_to_final_score(base_score, wallet_adjustment, {})
    )

    score_ctx = {
        "final_score": round(final_score, 4),
        "heuristic_ratio": float(early.get("heuristic_ratio") or 0.0),
    }
    routed = route_score(token_ctx, score_ctx, settings)

    if routed["hard_override"]:
        score_ctx["final_score"] = min(score_ctx["final_score"], 35.0)

    flags = set()
    warnings = set()
    for part in (
        early,
        bundle_bonus,
        cluster_adjustment,
        bundle_risk,
        x_bonus,
        rug,
        spam,
        conf,
    ):
        flags.update(part.get("flags", []))
        warnings.update(part.get("warnings", []))
    warnings.update(routed.get("route_warnings", []))

    return {
        "token_address": str(token_ctx.get("token_address") or ""),
        "symbol": str(token_ctx.get("symbol") or ""),
        "name": str(token_ctx.get("name") or ""),
        "fast_prescore": float(token_ctx.get("fast_prescore") or 0.0),
        **copy_bundle_contract_fields(token_ctx),
        **copy_short_horizon_contract_fields(token_ctx),
        "onchain_core": round(float(onchain["onchain_core"]), 4),
        "early_signal_bonus": round(float(early["early_signal_bonus"]), 4),
        "bundle_aggression_bonus": round(
            float(bundle_bonus["bundle_aggression_bonus"]), 4
        ),
        "organic_multi_cluster_bonus": round(
            float(cluster_adjustment["organic_multi_cluster_bonus"]), 4
        ),
        "single_cluster_penalty": round(
            float(cluster_adjustment["single_cluster_penalty"]), 4
        ),
        "creator_cluster_penalty": round(
            float(cluster_adjustment["creator_cluster_penalty"]), 4
        ),
        "bundle_sell_heavy_penalty": round(
            float(bundle_risk["bundle_sell_heavy_penalty"]), 4
        ),
        "retry_manipulation_penalty": round(
            float(bundle_risk["retry_manipulation_penalty"]), 4
        ),
        "x_validation_bonus": round(float(x_bonus["x_validation_bonus"]), 4),
        "rug_penalty": round(float(rug["rug_penalty"]), 4),
        "spam_penalty": round(float(spam["spam_penalty"]), 4),
        "confidence_adjustment": round(confidence_adjustment, 4),
        "wallet_adjustment": wallet_adjustment,
        "final_score": round(float(score_ctx["final_score"]), 4),
        "regime_candidate": routed["regime_candidate"],
        "score_inputs_status": _status_block(token_ctx),
        "score_flags": sorted(flags),
        "score_warnings": sorted(warnings),
        "scored_at": utc_now_iso(),
        "contract_version": settings.UNIFIED_SCORE_CONTRACT_VERSION,
    }


def score_tokens(tokens: list[dict], settings: Any) -> list[dict]:
    scored = [score_token(token_ctx=item, settings=settings) for item in tokens]
    scored.sort(key=lambda item: item.get("token_address", ""))
    return scored
