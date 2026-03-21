"""Unified scoring component calculators."""

from __future__ import annotations

from typing import Any

from analytics.evidence_quality import derive_evidence_quality
from analytics.score_normalizers import (
    normalize_capped,
    normalize_inverse,
    normalize_log_scaled,
    normalize_unit_interval,
)


X_DEGRADED_STATES = {"degraded", "timeout", "login_required", "captcha", "soft_ban"}
SELL_HEAVY_BUNDLE_COMPOSITIONS = {
    "sell-only": 1.0,
    "sell_heavy": 0.75,
    "sell-heavy": 0.75,
    "mostly-sell": 0.65,
}
RETRY_MANIPULATION_KEYWORDS = {
    "heavy": 0.75,
    "high": 0.75,
    "aggressive": 0.85,
    "loop": 0.8,
    "manip": 1.0,
    "retry": 0.6,
}


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _weighted_average(metrics: list[tuple[float | None, float]]) -> tuple[float, int]:
    present = [(value, weight) for value, weight in metrics if value is not None]
    if not present:
        return 0.0, 0
    total_weight = sum(weight for _, weight in present)
    if total_weight <= 0:
        return 0.0, 0
    weighted = sum(float(value) * weight for value, weight in present) / total_weight
    return _clamp01(weighted), len(present)


def _coverage_multiplier(present_count: int, total_count: int) -> float:
    if total_count <= 0 or present_count <= 0:
        return 0.0
    return _clamp01(present_count / total_count)


def compute_onchain_core(token_ctx: dict, settings: Any) -> dict:
    fast_prescore = normalize_capped(_f(token_ctx.get("fast_prescore")), 0, 100)
    holder_growth = normalize_log_scaled(
        max(_f(token_ctx.get("holder_growth_5m")) or 0.0, 1.0), 1.0, 120.0
    )
    smart_hits = normalize_capped(_f(token_ctx.get("smart_wallet_hits")), 0, 8)
    holder_dist = normalize_inverse(_f(token_ctx.get("top20_holder_share")), 0.20, 0.85)
    dev_quality = normalize_inverse(
        _f(token_ctx.get("dev_sell_pressure_5m")),
        0.02,
        settings.RUG_DEV_SELL_PRESSURE_HARD,
    )

    raw = (
        0.42 * fast_prescore
        + 0.18 * holder_growth
        + 0.14 * smart_hits
        + 0.14 * holder_dist
        + 0.12 * dev_quality
    )
    return {"onchain_core": round(raw * 45.0, 4)}


def compute_early_signal_bonus(token_ctx: dict, settings: Any) -> dict:
    floor = float(settings.UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR)
    heur_mult = max(0.0, min(1.0, max(floor, 0.75)))

    buy_ratio = normalize_unit_interval(_f(token_ctx.get("first30s_buy_ratio")))
    bundle = normalize_unit_interval(_f(token_ctx.get("bundle_cluster_score")))
    priority_fee = normalize_log_scaled(
        max(_f(token_ctx.get("priority_fee_avg_first_min")) or 0.00001, 0.00001),
        0.00001,
        0.005,
    )
    migration_speed = (
        normalize_inverse(_f(token_ctx.get("pumpfun_to_raydium_sec")), 45, 900)
        * heur_mult
    )
    entropy = (
        normalize_capped(_f(token_ctx.get("holder_entropy_est")), 1.0, 4.0) * heur_mult
    )
    first50_quality = (
        normalize_inverse(_f(token_ctx.get("first50_holder_conc_est")), 0.25, 0.85)
        * heur_mult
    )

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
    if (
        token_ctx.get("holder_entropy_est") is not None
        or token_ctx.get("first50_holder_conc_est") is not None
    ):
        flags.append("heuristic_holder_metrics")
        warnings.append("first50_holder_conc_est is heuristic")
    return {
        "early_signal_bonus": round(raw * 25.0, 4),
        "flags": flags,
        "warnings": warnings,
        "heuristic_ratio": 0.40,
    }


def compute_bundle_aggression_bonus(token_ctx: dict, settings: Any) -> dict:
    metrics = [
        (normalize_capped(_f(token_ctx.get("bundle_count_first_60s")), 1, 6), 0.20),
        (
            normalize_log_scaled(
                max(_f(token_ctx.get("bundle_size_value")) or 1.0, 1.0), 1.0, 50000.0
            ),
            0.18,
        ),
        (
            normalize_capped(
                _f(token_ctx.get("unique_wallets_per_bundle_avg")), 1.0, 5.0
            ),
            0.16,
        ),
        (
            normalize_inverse(
                _f(token_ctx.get("bundle_timing_from_liquidity_add_min")), 0.10, 8.0
            ),
            0.18,
        ),
        (normalize_unit_interval(_f(token_ctx.get("bundle_success_rate"))), 0.12),
        (normalize_unit_interval(_f(token_ctx.get("bundle_tip_efficiency"))), 0.08),
        (
            normalize_inverse(
                _f(token_ctx.get("cross_block_bundle_correlation")), 0.15, 0.95
            ),
            0.08,
        ),
    ]
    raw, present_count = _weighted_average(metrics)
    coverage = _coverage_multiplier(present_count, len(metrics))
    bonus = raw * coverage * float(settings.UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX)

    flags: list[str] = []
    warnings: list[str] = []
    if bonus >= float(settings.UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX) * 0.45:
        flags.append("bundle_aggression_positive")
    if 0 < present_count < 3:
        warnings.append("bundle_aggression_partial_evidence")

    return {
        "bundle_aggression_bonus": round(bonus, 4),
        "flags": flags,
        "warnings": warnings,
    }


def compute_cluster_quality_adjustment(token_ctx: dict, settings: Any) -> dict:
    organic_metrics = [
        (
            normalize_capped(
                _f(token_ctx.get("num_unique_clusters_first_60s")), 1.0, 5.0
            ),
            0.45,
        ),
        (
            normalize_inverse(
                _f(token_ctx.get("cluster_concentration_ratio")), 0.35, 0.90
            ),
            0.35,
        ),
        (
            normalize_inverse(
                _f(token_ctx.get("bundle_wallet_clustering_score")), 0.25, 1.0
            ),
            0.20,
        ),
    ]
    organic_raw, organic_present = _weighted_average(organic_metrics)
    organic_coverage = _coverage_multiplier(organic_present, len(organic_metrics))
    organic_bonus = (
        organic_raw
        * organic_coverage
        * float(settings.UNIFIED_SCORE_MULTI_CLUSTER_BONUS_MAX)
    )

    penalty_metrics = [
        (
            normalize_capped(
                _f(token_ctx.get("cluster_concentration_ratio")), 0.55, 1.0
            ),
            0.45,
        ),
        (
            normalize_capped(
                _f(token_ctx.get("bundle_wallet_clustering_score")), 0.55, 1.0
            ),
            0.40,
        ),
        (
            normalize_inverse(
                _f(token_ctx.get("num_unique_clusters_first_60s")), 1.0, 4.0
            ),
            0.15,
        ),
    ]
    penalty_raw, penalty_present = _weighted_average(penalty_metrics)
    penalty_coverage = _coverage_multiplier(penalty_present, len(penalty_metrics))
    single_cluster_penalty = (
        penalty_raw
        * penalty_coverage
        * float(settings.UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX)
    )

    creator_cluster_penalty = 0.0
    creator_cluster_link = _f(token_ctx.get("creator_cluster_link_score"))
    linkage_confidence = _f(token_ctx.get("linkage_confidence")) or 0.0
    shared_funder_link = _f(token_ctx.get("shared_funder_link_score"))
    cluster_dev_link = _f(token_ctx.get("cluster_dev_link_score"))

    if token_ctx.get("creator_in_cluster_flag") is True:
        creator_cluster_penalty = float(settings.UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY)
    elif creator_cluster_link is not None and creator_cluster_link >= 0.65 and linkage_confidence >= 0.55:
        creator_cluster_penalty = float(settings.UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY) * 0.75

    cluster_dev_link_penalty = 0.0
    if cluster_dev_link is not None and linkage_confidence >= 0.45:
        cluster_dev_link_penalty = (
            max(0.0, min(1.0, cluster_dev_link))
            * max(0.0, min(1.0, linkage_confidence))
            * float(getattr(settings, "UNIFIED_SCORE_CLUSTER_DEV_LINK_PENALTY_MAX", 3.0))
        )

    shared_funder_penalty = 0.0
    if shared_funder_link is not None and linkage_confidence >= 0.45:
        shared_funder_penalty = (
            max(0.0, min(1.0, shared_funder_link))
            * max(0.0, min(1.0, linkage_confidence))
            * float(getattr(settings, "UNIFIED_SCORE_SHARED_FUNDER_PENALTY_MAX", 2.5))
        )

    flags: list[str] = []
    if organic_bonus >= float(settings.UNIFIED_SCORE_MULTI_CLUSTER_BONUS_MAX) * 0.4:
        flags.append("organic_multi_cluster_participation")
    if (
        single_cluster_penalty
        >= float(settings.UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX) * 0.4
    ):
        flags.append("single_cluster_concentration")
    if creator_cluster_penalty > 0:
        flags.append("creator_cluster_linked")
    if cluster_dev_link_penalty > 0:
        flags.append("cluster_dev_link_penalty")
    if shared_funder_penalty > 0:
        flags.append("shared_funder_penalty")

    return {
        "organic_multi_cluster_bonus": round(organic_bonus, 4),
        "single_cluster_penalty": round(single_cluster_penalty, 4),
        "creator_cluster_penalty": round(creator_cluster_penalty, 4),
        "cluster_dev_link_penalty": round(cluster_dev_link_penalty, 4),
        "shared_funder_penalty": round(shared_funder_penalty, 4),
        "flags": flags,
        "warnings": [],
    }


def compute_continuation_quality_adjustment(token_ctx: dict, settings: Any) -> dict:
    continuation_confidence = str(token_ctx.get("continuation_confidence") or "").lower()
    continuation_status = str(token_ctx.get("continuation_status") or "").lower()
    coverage_ratio = normalize_unit_interval(_f(token_ctx.get("continuation_coverage_ratio")))

    confidence_multiplier = {
        "high": 1.0,
        "medium": 0.75,
        "low": 0.4,
    }.get(continuation_confidence, 1.0 if coverage_ratio >= 0.85 else 0.8)
    if continuation_status == "partial":
        confidence_multiplier *= 0.8
    elif continuation_status == "missing":
        confidence_multiplier = 0.0
    if coverage_ratio is not None and coverage_ratio > 0:
        confidence_multiplier *= max(0.35, coverage_ratio)

    organic_buyer_flow_raw = normalize_capped(
        _f(token_ctx.get("net_unique_buyers_60s")), 2.0, 18.0
    )
    organic_buyer_flow_bonus = organic_buyer_flow_raw * float(
        settings.UNIFIED_SCORE_ORGANIC_BUYER_FLOW_MAX
    ) * confidence_multiplier

    liquidity_refill_raw = normalize_capped(
        _f(token_ctx.get("liquidity_refill_ratio_120s")), 0.90, 1.80
    )
    liquidity_refill_bonus = liquidity_refill_raw * float(
        settings.UNIFIED_SCORE_LIQUIDITY_REFILL_MAX
    ) * confidence_multiplier

    smart_wallet_dispersion_raw = normalize_capped(
        _f(token_ctx.get("smart_wallet_dispersion_score")), 0.35, 0.90
    )
    smart_wallet_dispersion_bonus = smart_wallet_dispersion_raw * float(
        settings.UNIFIED_SCORE_SMART_WALLET_DISPERSION_MAX
    ) * confidence_multiplier

    x_author_velocity_raw = normalize_capped(
        _f(token_ctx.get("x_author_velocity_5m")), 1.10, 2.80
    )
    x_author_velocity_bonus = x_author_velocity_raw * float(
        settings.UNIFIED_SCORE_X_AUTHOR_VELOCITY_MAX
    ) * confidence_multiplier

    seller_reentry_raw = normalize_capped(
        _f(token_ctx.get("seller_reentry_ratio")), 0.18, 0.72
    )
    seller_reentry_bonus = seller_reentry_raw * float(
        settings.UNIFIED_SCORE_SELLER_REENTRY_MAX
    ) * confidence_multiplier

    shock_recovery_raw = normalize_inverse(
        _f(token_ctx.get("liquidity_shock_recovery_sec")), 20.0, 180.0
    )
    shock_recovery_bonus = shock_recovery_raw * float(
        settings.UNIFIED_SCORE_SHOCK_RECOVERY_MAX
    ) * confidence_multiplier

    cluster_distribution_risk_raw = normalize_capped(
        _f(token_ctx.get("cluster_sell_concentration_120s")), 0.45, 0.90
    )
    cluster_distribution_risk_penalty = cluster_distribution_risk_raw * float(
        settings.UNIFIED_SCORE_CLUSTER_DISTRIBUTION_RISK_MAX
    ) * max(confidence_multiplier, 0.5 if cluster_distribution_risk_raw > 0 else 0.0)

    flags: list[str] = []
    warnings: list[str] = []
    positive_components = {
        "organic_buyer_flow_bonus": organic_buyer_flow_bonus,
        "liquidity_refill_bonus": liquidity_refill_bonus,
        "smart_wallet_dispersion_bonus": smart_wallet_dispersion_bonus,
        "x_author_velocity_bonus": x_author_velocity_bonus,
        "seller_reentry_bonus": seller_reentry_bonus,
        "shock_recovery_bonus": shock_recovery_bonus,
    }
    evidence_present = sum(
        1
        for field in (
            "net_unique_buyers_60s",
            "liquidity_refill_ratio_120s",
            "smart_wallet_dispersion_score",
            "x_author_velocity_5m",
            "seller_reentry_ratio",
            "liquidity_shock_recovery_sec",
            "cluster_sell_concentration_120s",
        )
        if token_ctx.get(field) is not None
    )

    if (
        organic_buyer_flow_bonus
        >= float(settings.UNIFIED_SCORE_ORGANIC_BUYER_FLOW_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("organic_buyer_flow_positive")
    if (
        liquidity_refill_bonus
        >= float(settings.UNIFIED_SCORE_LIQUIDITY_REFILL_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("liquidity_refill_positive")
    if (
        smart_wallet_dispersion_bonus
        >= float(settings.UNIFIED_SCORE_SMART_WALLET_DISPERSION_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("smart_wallet_dispersion_positive")
    if (
        x_author_velocity_bonus
        >= float(settings.UNIFIED_SCORE_X_AUTHOR_VELOCITY_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("x_author_velocity_expanding")
    if (
        seller_reentry_bonus
        >= float(settings.UNIFIED_SCORE_SELLER_REENTRY_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("seller_reentry_supportive")
    if (
        shock_recovery_bonus
        >= float(settings.UNIFIED_SCORE_SHOCK_RECOVERY_MAX) * 0.4 * max(confidence_multiplier, 0.4)
    ):
        flags.append("liquidity_shock_recovered_fast")
    if (
        cluster_distribution_risk_penalty
        >= float(settings.UNIFIED_SCORE_CLUSTER_DISTRIBUTION_RISK_MAX) * 0.4 * max(confidence_multiplier, 0.5)
    ):
        flags.append("cluster_distribution_risk")

    if evidence_present and evidence_present < 3:
        warnings.append("continuation_quality_partial_evidence")
    if continuation_status in {"partial", "missing"}:
        warnings.append(f"continuation_status={continuation_status}")
    if continuation_confidence == "low":
        warnings.append("continuation_confidence_low")
    if sum(1 for value in positive_components.values() if value > 0) >= 3 and confidence_multiplier > 0:
        flags.append("continuation_quality_supported")

    return {
        "organic_buyer_flow_bonus": round(organic_buyer_flow_bonus, 4),
        "liquidity_refill_bonus": round(liquidity_refill_bonus, 4),
        "smart_wallet_dispersion_bonus": round(smart_wallet_dispersion_bonus, 4),
        "x_author_velocity_bonus": round(x_author_velocity_bonus, 4),
        "seller_reentry_bonus": round(seller_reentry_bonus, 4),
        "shock_recovery_bonus": round(shock_recovery_bonus, 4),
        "cluster_distribution_risk_penalty": round(
            cluster_distribution_risk_penalty, 4
        ),
        "flags": flags,
        "warnings": warnings,
    }


def compute_bundle_risk_penalties(token_ctx: dict, settings: Any) -> dict:
    composition = (
        str(token_ctx.get("bundle_composition_dominant") or "").strip().lower()
    )
    sell_heavy_penalty = SELL_HEAVY_BUNDLE_COMPOSITIONS.get(composition, 0.0) * float(
        settings.UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX
    )

    retry_value = token_ctx.get("bundle_failure_retry_pattern")
    retry_raw = 0.0
    retry_numeric = _f(retry_value)
    if retry_numeric is not None:
        retry_raw = normalize_capped(retry_numeric, 1.0, 5.0)
    elif retry_value is not None:
        retry_text = str(retry_value).strip().lower()
        retry_raw = max(
            (
                weight
                for keyword, weight in RETRY_MANIPULATION_KEYWORDS.items()
                if keyword in retry_text
            ),
            default=0.0,
        )
    retry_manipulation_penalty = retry_raw * float(
        settings.UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX
    )

    flags: list[str] = []
    if sell_heavy_penalty > 0:
        flags.append("bundle_sell_heavy")
    if (
        retry_manipulation_penalty
        >= float(settings.UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX) * 0.4
    ):
        flags.append("bundle_retry_pattern_suspicious")

    return {
        "bundle_sell_heavy_penalty": round(sell_heavy_penalty, 4),
        "retry_manipulation_penalty": round(retry_manipulation_penalty, 4),
        "flags": flags,
        "warnings": [],
    }



def compute_evidence_quality_penalties(
    token_ctx: dict,
    settings: Any,
    evidence_quality: dict[str, Any] | None = None,
) -> dict:
    summary = evidence_quality or derive_evidence_quality(token_ctx)
    partial_evidence_penalty = 0.0
    if bool(summary.get("partial_evidence_flag")):
        partial_evidence_penalty = float(getattr(settings, "UNIFIED_SCORE_PARTIAL_EVIDENCE_PENALTY", 1.5))

    threshold = float(getattr(settings, "UNIFIED_SCORE_EVIDENCE_LOW_CONFIDENCE_THRESHOLD", 0.55))
    max_penalty = float(getattr(settings, "UNIFIED_SCORE_LOW_CONFIDENCE_EVIDENCE_PENALTY_MAX", 3.0))
    conflict_bonus = float(getattr(settings, "UNIFIED_SCORE_EVIDENCE_CONFLICT_PENALTY_BONUS", 0.75))

    evidence_quality_score = max(0.0, min(1.0, _f(summary.get("evidence_quality_score")) or 0.0))
    evidence_coverage_ratio = max(0.0, min(1.0, _f(summary.get("evidence_coverage_ratio")) or _f(summary.get("coverage_ratio")) or 0.0))

    low_confidence_evidence_penalty = 0.0
    if evidence_quality_score < threshold:
        shortfall_ratio = (threshold - evidence_quality_score) / max(threshold, 1e-6)
        coverage_multiplier = 1.0 + min(0.25, max(0.0, threshold - evidence_coverage_ratio))
        low_confidence_evidence_penalty = shortfall_ratio * max_penalty * coverage_multiplier
    if bool(summary.get("evidence_conflict_flag")):
        low_confidence_evidence_penalty += conflict_bonus
    low_confidence_evidence_penalty = min(max_penalty, max(0.0, low_confidence_evidence_penalty))

    flags: list[str] = []
    warnings: list[str] = []
    if partial_evidence_penalty > 0:
        flags.append("partial_evidence_score_penalty")
        warnings.append("partial_evidence_flag=true")
    if low_confidence_evidence_penalty > 0:
        flags.append("low_confidence_evidence_score_penalty")
        warnings.append("low_confidence_evidence_quality")
    if bool(summary.get("evidence_conflict_flag")):
        flags.append("evidence_conflict_score_penalty")
        warnings.append("evidence_conflict_flag=true")

    return {
        "partial_evidence_penalty": round(partial_evidence_penalty, 4),
        "low_confidence_evidence_penalty": round(low_confidence_evidence_penalty, 4),
        "flags": flags,
        "warnings": warnings,
    }

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
    if (_f(token_ctx.get("dev_sell_pressure_5m")) or 0.0) >= float(
        settings.RUG_DEV_SELL_PRESSURE_WARN
    ):
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

    missing_keys = [
        k
        for k in ("fast_prescore", "rug_score", "rug_verdict")
        if token_ctx.get(k) is None
    ]
    if missing_keys:
        adj -= min(10.0, 3.0 + (len(missing_keys) - 1) * 2.0)

    for opt_key in (
        "x_validation_score",
        "x_status",
        "holder_growth_5m",
        "dev_sell_pressure_5m",
        "smart_wallet_hits",
    ):
        if token_ctx.get(opt_key) is None:
            adj -= 0.5

    return {"confidence_adjustment": round(adj, 4), "flags": flags}
