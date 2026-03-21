"""Unified scoring orchestration across on-chain, X, rug, and wallet layers."""

from __future__ import annotations

from typing import Any, Mapping

from analytics.evidence_quality import derive_evidence_quality
from analytics.score_components import (
    compute_bundle_aggression_bonus,
    compute_bundle_risk_penalties,
    compute_cluster_quality_adjustment,
    compute_continuation_quality_adjustment,
    compute_confidence_adjustment,
    compute_evidence_quality_penalties,
    compute_early_signal_bonus,
    compute_onchain_core,
    compute_rug_penalty,
    compute_spam_penalty,
    compute_x_validation_bonus,
)
from analytics.score_router import route_score
from analytics.wallet_weighting import (
    build_wallet_adjustment_compat,
    compute_wallet_weighting,
)
from utils.bundle_contract_fields import (
    copy_bundle_contract_fields,
    copy_linkage_contract_fields,
)
from utils.clock import utc_now_iso
from utils.short_horizon_contract_fields import copy_short_horizon_contract_fields
from utils.wallet_family_contract_fields import copy_wallet_family_contract_fields


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _status_block(token_ctx: Mapping[str, Any]) -> dict[str, Any]:
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


def _resolve_scored_at(token_ctx: Mapping[str, Any], explicit_scored_at: str | None) -> str:
    if explicit_scored_at:
        return str(explicit_scored_at)
    for key in (
        "scored_at",
        "score_timestamp",
        "timestamp",
        "snapshot_ts",
        "snapshot_at",
        "observed_at",
        "event_ts",
        "as_of",
        "as_of_ts",
    ):
        value = token_ctx.get(key)
        if value:
            return str(value)
    return utc_now_iso()


def score_token(
    token_ctx: dict,
    settings: Any,
    *,
    wallet_weighting_mode: str | None = None,
    scored_at: str | None = None,
) -> dict:
    onchain = compute_onchain_core(token_ctx, settings)
    early = compute_early_signal_bonus(token_ctx, settings)
    bundle_bonus = compute_bundle_aggression_bonus(token_ctx, settings)
    cluster_adjustment = compute_cluster_quality_adjustment(token_ctx, settings)
    continuation_quality = compute_continuation_quality_adjustment(token_ctx, settings)
    bundle_risk = compute_bundle_risk_penalties(token_ctx, settings)
    x_bonus = compute_x_validation_bonus(token_ctx, settings)
    rug = compute_rug_penalty(token_ctx, settings)
    spam = compute_spam_penalty(token_ctx, settings)
    conf = compute_confidence_adjustment(token_ctx, settings)
    evidence_quality = derive_evidence_quality(token_ctx)
    evidence_penalties = compute_evidence_quality_penalties(token_ctx, settings, evidence_quality)
    discovery_lag = _discovery_lag_penalty(token_ctx, settings)

    confidence_adjustment = float(conf.get("confidence_adjustment") or 0.0) + float(
        x_bonus.get("confidence_adjustment") or 0.0
    )

    base_score = _clamp(
        float(onchain["onchain_core"])
        + float(early["early_signal_bonus"])
        + float(bundle_bonus["bundle_aggression_bonus"])
        + float(cluster_adjustment["organic_multi_cluster_bonus"])
        + float(continuation_quality["organic_buyer_flow_bonus"])
        + float(continuation_quality["liquidity_refill_bonus"])
        + float(continuation_quality["smart_wallet_dispersion_bonus"])
        + float(continuation_quality["x_author_velocity_bonus"])
        + float(continuation_quality["seller_reentry_bonus"])
        + float(continuation_quality["shock_recovery_bonus"])
        + float(x_bonus["x_validation_bonus"])
        - float(cluster_adjustment["single_cluster_penalty"])
        - float(cluster_adjustment["creator_cluster_penalty"])
        - float(cluster_adjustment["cluster_dev_link_penalty"])
        - float(cluster_adjustment["shared_funder_penalty"])
        - float(continuation_quality["cluster_distribution_risk_penalty"])
        - float(bundle_risk["bundle_sell_heavy_penalty"])
        - float(bundle_risk["retry_manipulation_penalty"])
        - float(rug["rug_penalty"])
        - float(spam["spam_penalty"])
        - float(evidence_penalties["partial_evidence_penalty"])
        - float(evidence_penalties["low_confidence_evidence_penalty"])
        - float(discovery_lag["penalty"])
        + confidence_adjustment
    )
    final_score_pre_wallet = _clamp(base_score)
    partial_review_score = _clamp(
        final_score_pre_wallet
        + float(evidence_penalties.get("partial_evidence_penalty") or 0.0)
        + float(evidence_penalties.get("low_confidence_evidence_penalty") or 0.0)
        + float(discovery_lag.get("penalty") or 0.0)
    )

    score_ctx = {
        "final_score": round(final_score_pre_wallet, 4),
        "partial_review_score": round(partial_review_score, 4),
        "heuristic_ratio": float(early.get("heuristic_ratio") or 0.0),
    }
    routed = route_score(token_ctx, score_ctx, settings)
    if routed["hard_override"]:
        score_ctx["final_score"] = min(score_ctx["final_score"], 35.0)
    final_score_pre_wallet = _clamp(float(score_ctx["final_score"]))

    wallet_weighting = compute_wallet_weighting(
        token_ctx,
        settings,
        requested_mode=wallet_weighting_mode,
    )
    final_score = final_score_pre_wallet + float(
        wallet_weighting.get("wallet_score_component_applied") or 0.0
    )
    if wallet_weighting.get("wallet_weighting_effective_mode") in {"off", "shadow", "degraded_zero"}:
        final_score = final_score_pre_wallet
    final_score = _clamp(final_score)

    flags = set()
    warnings = set()
    for part in (
        early,
        bundle_bonus,
        cluster_adjustment,
        continuation_quality,
        bundle_risk,
        x_bonus,
        rug,
        spam,
        conf,
        evidence_penalties,
        discovery_lag,
    ):
        flags.update(part.get("flags", []))
        warnings.update(part.get("warnings", []))
    warnings.update(routed.get("route_warnings", []))
    warnings.update(evidence_quality.get("evidence_quality_warnings", []))

    scored_at_value = _resolve_scored_at(token_ctx, scored_at)
    wallet_adjustment = build_wallet_adjustment_compat(wallet_weighting)

    return {
        "token_address": str(token_ctx.get("token_address") or ""),
        "symbol": str(token_ctx.get("symbol") or ""),
        "name": str(token_ctx.get("name") or ""),
        "fast_prescore": float(token_ctx.get("fast_prescore") or 0.0),
        **copy_bundle_contract_fields(token_ctx),
        **copy_linkage_contract_fields(token_ctx),
        **copy_short_horizon_contract_fields(token_ctx),
        **copy_wallet_family_contract_fields(token_ctx),
        "onchain_core": round(float(onchain["onchain_core"]), 4),
        "early_signal_bonus": round(float(early["early_signal_bonus"]), 4),
        "bundle_aggression_bonus": round(float(bundle_bonus["bundle_aggression_bonus"]), 4),
        "organic_multi_cluster_bonus": round(float(cluster_adjustment["organic_multi_cluster_bonus"]), 4),
        "single_cluster_penalty": round(float(cluster_adjustment["single_cluster_penalty"]), 4),
        "creator_cluster_penalty": round(float(cluster_adjustment["creator_cluster_penalty"]), 4),
        "cluster_dev_link_penalty": round(float(cluster_adjustment["cluster_dev_link_penalty"]), 4),
        "shared_funder_penalty": round(float(cluster_adjustment["shared_funder_penalty"]), 4),
        "organic_buyer_flow_bonus": round(float(continuation_quality["organic_buyer_flow_bonus"]), 4),
        "liquidity_refill_bonus": round(float(continuation_quality["liquidity_refill_bonus"]), 4),
        "smart_wallet_dispersion_bonus": round(float(continuation_quality["smart_wallet_dispersion_bonus"]), 4),
        "x_author_velocity_bonus": round(float(continuation_quality["x_author_velocity_bonus"]), 4),
        "seller_reentry_bonus": round(float(continuation_quality["seller_reentry_bonus"]), 4),
        "shock_recovery_bonus": round(float(continuation_quality["shock_recovery_bonus"]), 4),
        "cluster_distribution_risk_penalty": round(float(continuation_quality["cluster_distribution_risk_penalty"]), 4),
        "bundle_sell_heavy_penalty": round(float(bundle_risk["bundle_sell_heavy_penalty"]), 4),
        "retry_manipulation_penalty": round(float(bundle_risk["retry_manipulation_penalty"]), 4),
        "x_validation_bonus": round(float(x_bonus["x_validation_bonus"]), 4),
        "rug_penalty": round(float(rug["rug_penalty"]), 4),
        "spam_penalty": round(float(spam["spam_penalty"]), 4),
        "confidence_adjustment": round(confidence_adjustment, 4),
        "evidence_quality_score": round(float(evidence_quality["evidence_quality_score"]), 4),
        "evidence_conflict_flag": bool(evidence_quality["evidence_conflict_flag"]),
        "partial_evidence_flag": bool(evidence_quality["partial_evidence_flag"]),
        "evidence_coverage_ratio": round(float(evidence_quality["evidence_coverage_ratio"]), 4),
        "evidence_available": list(evidence_quality["evidence_available"]),
        "evidence_scores": dict(evidence_quality["evidence_scores"]),
        "partial_evidence_penalty": round(float(evidence_penalties["partial_evidence_penalty"]), 4),
        "low_confidence_evidence_penalty": round(float(evidence_penalties["low_confidence_evidence_penalty"]), 4),
        "discovery_lag_score_penalty": round(float(discovery_lag["penalty"]), 4),
        "wallet_adjustment": wallet_adjustment,
        "wallet_weighting_mode": wallet_weighting["wallet_weighting_mode"],
        "wallet_weighting_effective_mode": wallet_weighting["wallet_weighting_effective_mode"],
        "wallet_registry_status": wallet_weighting["wallet_registry_status"],
        "wallet_score_component_raw": round(float(wallet_weighting["wallet_score_component_raw"]), 6),
        "wallet_score_component_applied": round(float(wallet_weighting["wallet_score_component_applied"]), 6),
        "wallet_score_component_applied_shadow": round(float(wallet_weighting["wallet_score_component_applied_shadow"]), 6),
        "wallet_score_component_capped": bool(wallet_weighting["wallet_score_component_capped"]),
        "wallet_score_component_reason": str(wallet_weighting["wallet_score_component_reason"]),
        "wallet_score_explain": dict(wallet_weighting["wallet_score_explain"]),
        "final_score_pre_wallet": round(final_score_pre_wallet, 4),
        "partial_review_score": round(partial_review_score, 4),
        "final_score": round(final_score, 4),
        "regime_candidate": routed["regime_candidate"],
        "score_inputs_status": _status_block(token_ctx),
        "score_flags": sorted(flags),
        "score_warnings": sorted(warnings),
        "scored_at": scored_at_value,
        "contract_version": settings.UNIFIED_SCORE_CONTRACT_VERSION,
    }


def score_tokens(
    tokens: list[dict],
    settings: Any,
    *,
    wallet_weighting_mode: str | None = None,
    scored_at: str | None = None,
) -> list[dict]:
    scored = [
        score_token(
            token_ctx=item,
            settings=settings,
            wallet_weighting_mode=wallet_weighting_mode,
            scored_at=scored_at,
        )
        for item in tokens
    ]
    scored.sort(key=lambda item: item.get("token_address", ""))
    return scored
