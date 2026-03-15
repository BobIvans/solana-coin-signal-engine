"""Unified scoring component calculators."""

from __future__ import annotations

from typing import Any

from analytics.score_normalizers import normalize_capped, normalize_inverse, normalize_log_scaled, normalize_unit_interval


X_DEGRADED_STATES = {"degraded", "timeout", "login_required", "captcha"}


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_onchain_core(token_ctx: dict, settings: Any) -> dict:
    fast_prescore = normalize_capped(_f(token_ctx.get("fast_prescore")), 0, 100)
    holder_growth = normalize_log_scaled(max(_f(token_ctx.get("holder_growth_5m")) or 0.0, 1.0), 1.0, 120.0)
    smart_hits = normalize_capped(_f(token_ctx.get("smart_wallet_hits")), 0, 8)
    holder_dist = normalize_inverse(_f(token_ctx.get("top20_holder_share")), 0.20, 0.85)
    dev_quality = normalize_inverse(_f(token_ctx.get("dev_sell_pressure_5m")), 0.02, settings.RUG_DEV_SELL_PRESSURE_HARD)

    raw = 0.42 * fast_prescore + 0.18 * holder_growth + 0.14 * smart_hits + 0.14 * holder_dist + 0.12 * dev_quality
    return {"onchain_core": round(raw * 45.0, 4)}


def compute_early_signal_bonus(token_ctx: dict, settings: Any) -> dict:
    floor = float(settings.UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR)
    heur_mult = max(0.0, min(1.0, max(floor, 0.75)))

    buy_ratio = normalize_unit_interval(_f(token_ctx.get("first30s_buy_ratio")))
    bundle = normalize_unit_interval(_f(token_ctx.get("bundle_cluster_score")))
    priority_fee = normalize_log_scaled(max(_f(token_ctx.get("priority_fee_avg_first_min")) or 0.00001, 0.00001), 0.00001, 0.005)
    migration_speed = normalize_inverse(_f(token_ctx.get("pumpfun_to_raydium_sec")), 45, 900) * heur_mult
    entropy = normalize_capped(_f(token_ctx.get("holder_entropy_est")), 1.0, 4.0) * heur_mult
    first50_quality = normalize_inverse(_f(token_ctx.get("first50_holder_conc_est")), 0.25, 0.85) * heur_mult

    raw = (
        0.24 * buy_ratio
        + 0.22 * bundle
        + 0.14 * priority_fee
        + 0.14 * migration_speed
        + 0.14 * entropy
        + 0.12 * first50_quality
    )
    flags: list[str] = []
    warnings: list[str] = []
    if token_ctx.get("holder_entropy_est") is not None or token_ctx.get("first50_holder_conc_est") is not None:
        flags.append("heuristic_holder_metrics")
        warnings.append("first50_holder_conc_est is heuristic")
    return {"early_signal_bonus": round(raw * 25.0, 4), "flags": flags, "warnings": warnings, "heuristic_ratio": 0.40}


def compute_x_validation_bonus(token_ctx: dict, settings: Any) -> dict:
    score_norm = normalize_capped(_f(token_ctx.get("x_validation_score")), 0, 100)
    delta_norm = normalize_capped(_f(token_ctx.get("x_validation_delta")), -40, 40)
    bonus = (0.65 * score_norm + 0.35 * delta_norm) * 14.0

    flags: list[str] = []
    warnings: list[str] = []
    confidence_adjustment = 0.0
    x_status = str(token_ctx.get("x_status") or "missing")

    if x_status in X_DEGRADED_STATES:
        flags.append("x_degraded")
        warnings.append(f"x_status={x_status}")
        bonus = min(bonus, 5.0)
        confidence_adjustment -= float(settings.UNIFIED_SCORE_X_DEGRADED_PENALTY)

    if token_ctx.get("x_validation_score") is None:
        warnings.append("x_validation_score_missing")

    return {
        "x_validation_bonus": round(max(0.0, bonus), 4),
        "flags": flags,
        "warnings": warnings,
        "confidence_adjustment": round(confidence_adjustment, 4),
    }


def compute_rug_penalty(token_ctx: dict, settings: Any) -> dict:
    rug_score = normalize_unit_interval(_f(token_ctx.get("rug_score")))
    rug_verdict = str(token_ctx.get("rug_verdict") or "WATCH").upper()
    penalty = rug_score * 30.0
    if rug_verdict == "WATCH":
        penalty += 2.0

    flags: list[str] = []
    if token_ctx.get("lp_burn_confirmed") is False:
        flags.append("lp_not_burned")
    if (_f(token_ctx.get("dev_sell_pressure_5m")) or 0.0) >= float(settings.RUG_DEV_SELL_PRESSURE_WARN):
        flags.append("dev_sell_pressure_warn")
    if rug_verdict == "IGNORE":
        flags.append("hard_rug_override")

    return {"rug_penalty": round(penalty, 4), "flags": flags}


def compute_spam_penalty(token_ctx: dict, settings: Any) -> dict:
    dup = normalize_unit_interval(_f(token_ctx.get("x_duplicate_text_ratio")))
    promoter = normalize_unit_interval(_f(token_ctx.get("x_promoter_concentration")))
    penalty = (0.55 * dup + 0.45 * promoter) * 8.0

    flags: list[str] = []
    warnings: list[str] = []
    unique = _f(token_ctx.get("x_unique_authors_visible")) or 0.0
    mention = _f(token_ctx.get("x_contract_mention_presence")) or 0.0
    if unique <= 2 and dup >= 0.6 and promoter >= 0.6 and mention > 0:
        flags.append("social_signal_may_be_manufactured")
        warnings.append("high_dup_and_promoter_concentration_with_low_unique_authors")

    return {"spam_penalty": round(penalty, 4), "flags": flags, "warnings": warnings}


def compute_confidence_adjustment(token_ctx: dict, settings: Any) -> dict:
    adj = 0.0
    flags: list[str] = []

    enrichment_status = str(token_ctx.get("enrichment_status") or "ok")
    rug_status = str(token_ctx.get("rug_status") or "ok")

    partial_penalty = float(settings.UNIFIED_SCORE_PARTIAL_DATA_PENALTY)
    if enrichment_status == "partial":
        flags.append("enrichment_partial")
        adj -= partial_penalty
    if rug_status == "partial":
        flags.append("rug_partial")
        adj -= partial_penalty + 1.0

    missing_keys = [k for k in ("fast_prescore", "rug_score", "rug_verdict") if token_ctx.get(k) is None]
    if missing_keys:
        adj -= min(10.0, 3.0 + (len(missing_keys) - 1) * 2.0)

    for opt_key in ("x_validation_score", "x_status", "holder_growth_5m", "dev_sell_pressure_5m", "smart_wallet_hits"):
        if token_ctx.get(opt_key) is None:
            adj -= 0.5

    return {"confidence_adjustment": round(adj, 4), "flags": flags}
