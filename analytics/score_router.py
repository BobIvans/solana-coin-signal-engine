"""Routing logic for unified token score outputs."""

from __future__ import annotations

from typing import Any


_PARTIAL_STATUSES = ("enrichment_status", "rug_status", "continuation_status")
_REQUIRED_FIELDS = ("token_address", "fast_prescore", "rug_score", "rug_verdict")


def _has_partial_evidence(token_ctx: dict) -> bool:
    return any(str(token_ctx.get(key) or "").lower() == "partial" for key in _PARTIAL_STATUSES)


def route_score(token_ctx: dict, score_ctx: dict, settings: Any) -> dict:
    final_score = float(score_ctx.get("final_score") or 0.0)
    partial_review_score = float(score_ctx.get("partial_review_score") or final_score)
    warnings: list[str] = []
    route = "IGNORE"

    entry_threshold = float(settings.UNIFIED_SCORE_ENTRY_THRESHOLD)
    watch_threshold = float(settings.UNIFIED_SCORE_WATCH_THRESHOLD)
    partial_review_buffer = float(
        getattr(settings, "UNIFIED_SCORE_PARTIAL_REVIEW_BUFFER", 1.0) or 0.0
    )

    if final_score >= entry_threshold:
        route = "ENTRY_CANDIDATE"
    elif final_score >= watch_threshold:
        route = "WATCHLIST"

    hard_override = False
    if str(token_ctx.get("rug_verdict") or "").upper() == "IGNORE":
        route = "IGNORE"
        hard_override = True
        warnings.append("hard_rug_override")

    mint_not_revoked = token_ctx.get("mint_revoked") is False
    if mint_not_revoked:
        route = "IGNORE"
        warnings.append("mint_not_revoked")

    dev_sell = float(token_ctx.get("dev_sell_pressure_5m") or 0.0)
    dev_sell_hard = dev_sell >= float(settings.RUG_DEV_SELL_PRESSURE_HARD)
    if dev_sell_hard:
        route = "IGNORE"
        warnings.append("dev_sell_pressure_hard")

    required_missing = [k for k in _REQUIRED_FIELDS if token_ctx.get(k) is None]
    if settings.UNIFIED_SCORING_REQUIRE_X and token_ctx.get("x_validation_score") is None:
        required_missing.append("x_validation_score")
    critical_missing = bool(required_missing and not settings.UNIFIED_SCORING_FAILOPEN)
    if critical_missing:
        route = "IGNORE"
        warnings.append(f"critical_missing:{','.join(required_missing)}")

    downgrade = False
    if route == "ENTRY_CANDIDATE":
        if str(token_ctx.get("x_status") or "") in {"degraded", "timeout", "login_required", "captcha", "soft_ban"}:
            route = "WATCHLIST"
            downgrade = True
            warnings.append("entry_downgraded_x_degraded")
        if str(token_ctx.get("enrichment_status") or "ok") == "partial":
            route = "WATCHLIST"
            downgrade = True
            warnings.append("entry_downgraded_enrichment_partial")
        if str(token_ctx.get("rug_status") or "ok") == "partial":
            route = "WATCHLIST"
            downgrade = True
            warnings.append("entry_downgraded_rug_partial")
        if float(score_ctx.get("heuristic_ratio") or 0.0) >= 0.6:
            route = "WATCHLIST"
            downgrade = True
            warnings.append("entry_downgraded_heuristic_heavy")

    partial_review_allowed = (
        route == "IGNORE"
        and not hard_override
        and not mint_not_revoked
        and not dev_sell_hard
        and not critical_missing
        and _has_partial_evidence(token_ctx)
        and final_score < watch_threshold
        and partial_review_score >= (watch_threshold - partial_review_buffer)
    )
    if partial_review_allowed:
        route = "WATCHLIST"
        warnings.append("watchlist_partial_evidence_review")

    return {
        "regime_candidate": route,
        "route_warnings": sorted(set(warnings)),
        "hard_override": hard_override,
        "downgraded": downgrade,
    }
