"""Score token-level X-validation metrics into 0..100 output."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(0.0, min(1.0, value / cap))


def score_x_validation(metrics: dict[str, Any], settings: Any) -> dict[str, Any]:
    if metrics.get("x_status") == "degraded":
        degraded_score = float(settings.OPENCLAW_X_DEGRADED_SCORE)
        return {
            **metrics,
            "x_validation_score": round(degraded_score, 2),
            "x_validation_delta": round(degraded_score - degraded_score, 2),
            "contract_version": settings.X_VALIDATION_CONTRACT_VERSION,
        }

    authors_norm = _norm(float(metrics.get("x_unique_authors_visible", 0.0) or 0.0), 20)
    posts_norm = _norm(float(metrics.get("x_posts_visible", 0.0) or 0.0), 30)
    engagement_norm = _norm(float(metrics.get("x_weighted_engagement", 0.0) or 0.0), 1500)
    official_match = float(metrics.get("x_official_account_match", 0) or 0)
    contract_mention = float(metrics.get("x_contract_mention_presence", 0) or 0)
    freshness_bonus = 1.0
    query_success_rate = _norm(float(metrics.get("x_queries_succeeded", 0.0) or 0.0), max(float(metrics.get("x_queries_attempted", 1) or 1), 1))
    duplicate_penalty = float(metrics.get("x_duplicate_text_ratio", 0.0) or 0.0)
    promoter_penalty = float(metrics.get("x_promoter_concentration", 0.0) or 0.0)

    score = (
        0.22 * authors_norm
        + 0.22 * posts_norm
        + 0.20 * engagement_norm
        + 0.12 * official_match
        + 0.10 * contract_mention
        + 0.08 * freshness_bonus
        + 0.06 * query_success_rate
        - 0.10 * duplicate_penalty
        - 0.08 * promoter_penalty
    ) * 100

    score = round(_clamp(score), 2)
    degraded_score = float(settings.OPENCLAW_X_DEGRADED_SCORE)

    return {
        **metrics,
        "x_validation_score": score,
        "x_validation_delta": round(score - degraded_score, 2),
        "contract_version": settings.X_VALIDATION_CONTRACT_VERSION,
    }
