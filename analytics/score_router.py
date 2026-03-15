"""Routing logic for unified token score outputs."""

from __future__ import annotations

from typing import Any


def route_score(token_ctx: dict, score_ctx: dict, settings: Any) -> dict:
    final_score = float(score_ctx.get("final_score") or 0.0)
    warnings: list[str] = []
    route = "IGNORE"

    if final_score >= float(settings.UNIFIED_SCORE_ENTRY_THRESHOLD):
        route = "ENTRY_CANDIDATE"
    elif final_score >= float(settings.UNIFIED_SCORE_WATCH_THRESHOLD):
        route = "WATCHLIST"

    hard_override = False
    if str(token_ctx.get("rug_verdict") or "").upper() == "IGNORE":
        route = "IGNORE"
        hard_override = True
        warnings.append("hard_rug_override")

    if token_ctx.get("mint_revoked") is False:
        route = "IGNORE"
        warnings.append("mint_not_revoked")

    dev_sell = float(token_ctx.get("dev_sell_pressure_5m") or 0.0)
    if dev_sell >= float(settings.RUG_DEV_SELL_PRESSURE_HARD):
        route = "IGNORE"
        warnings.append("dev_sell_pressure_hard")

    required_missing = [k for k in ("token_address", "fast_prescore", "rug_score", "rug_verdict") if token_ctx.get(k) is None]
    if settings.UNIFIED_SCORING_REQUIRE_X and token_ctx.get("x_validation_score") is None:
        required_missing.append("x_validation_score")
    if required_missing and not settings.UNIFIED_SCORING_FAILOPEN:
        route = "IGNORE"
        warnings.append(f"critical_missing:{','.join(required_missing)}")

    downgrade = False
    if route == "ENTRY_CANDIDATE":
        if str(token_ctx.get("x_status") or "") in {"degraded", "timeout", "login_required", "captcha"}:
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

    return {
        "regime_candidate": route,
        "route_warnings": sorted(set(warnings)),
        "hard_override": hard_override,
        "downgraded": downgrade,
    }
