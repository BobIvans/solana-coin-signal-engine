from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics.unified_score import score_token
from trading.entry_logic import decide_entry
from trading.entry_snapshot import build_entry_snapshot
from trading.exit_logic import decide_exit
from utils.clock import utc_now_iso


class FalsePositiveSettings:
    UNIFIED_SCORE_HEURISTIC_CONFIDENCE_FLOOR = 0.55
    UNIFIED_SCORE_BUNDLE_AGGRESSION_MAX = 7.0
    UNIFIED_SCORE_MULTI_CLUSTER_BONUS_MAX = 6.0
    UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX = 8.0
    UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY = 6.0
    UNIFIED_SCORE_CLUSTER_DEV_LINK_PENALTY_MAX = 3.0
    UNIFIED_SCORE_SHARED_FUNDER_PENALTY_MAX = 2.5
    UNIFIED_SCORE_ORGANIC_BUYER_FLOW_MAX = 3.0
    UNIFIED_SCORE_LIQUIDITY_REFILL_MAX = 3.0
    UNIFIED_SCORE_SMART_WALLET_DISPERSION_MAX = 2.0
    UNIFIED_SCORE_X_AUTHOR_VELOCITY_MAX = 2.0
    UNIFIED_SCORE_SELLER_REENTRY_MAX = 2.0
    UNIFIED_SCORE_SHOCK_RECOVERY_MAX = 2.0
    UNIFIED_SCORE_CLUSTER_DISTRIBUTION_RISK_MAX = 4.0
    UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX = 6.0
    UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX = 6.0
    UNIFIED_SCORE_X_DEGRADED_PENALTY = 3.0
    UNIFIED_SCORE_PARTIAL_DATA_PENALTY = 2.5
    UNIFIED_SCORE_ENTRY_THRESHOLD = 72.0
    UNIFIED_SCORE_WATCH_THRESHOLD = 55.0
    UNIFIED_SCORING_REQUIRE_X = False
    UNIFIED_SCORING_FAILOPEN = False
    UNIFIED_SCORE_CONTRACT_VERSION = "unified_score_v1"

    RUG_DEV_SELL_PRESSURE_HARD = 0.25
    RUG_DEV_SELL_PRESSURE_WARN = 0.10

    WALLET_TIER1_BONUS_SCORE = 3.0
    WALLET_TIER2_BONUS_SCORE = 1.0
    WALLET_EARLY_ENTRY_BONUS_SCORE = 2.0
    WALLET_NEGATIVE_NETFLOW_PENALTY = 3.0
    WALLET_MAX_BONUS_SCORE = 6.0

    ENTRY_SELECTOR_FAILCLOSED = True
    ENTRY_SCALP_SCORE_MIN = 82
    ENTRY_TREND_SCORE_MIN = 86
    ENTRY_SCALP_MAX_AGE_SEC = 480
    ENTRY_RUG_MAX_SCALP = 0.30
    ENTRY_RUG_MAX_TREND = 0.20
    ENTRY_BUY_PRESSURE_MIN_SCALP = 0.75
    ENTRY_BUY_PRESSURE_MIN_TREND = 0.65
    ENTRY_FIRST30S_BUY_RATIO_MIN = 0.65
    ENTRY_BUNDLE_CLUSTER_MIN = 0.55
    ENTRY_SCALP_MIN_X_SCORE = 50
    ENTRY_TREND_MIN_X_SCORE = 65
    ENTRY_HOLDER_GROWTH_MIN_TREND = 20
    ENTRY_SMART_WALLET_HITS_MIN_TREND = 2
    ENTRY_TREND_MULTI_CLUSTER_MIN = 3
    ENTRY_TREND_CLUSTER_CONCENTRATION_MAX = 0.55
    ENTRY_TREND_DEV_SELL_MAX = 0.02
    ENTRY_SCALP_BUNDLE_COUNT_MIN = 2
    ENTRY_REGIME_CONFIDENCE_FLOOR_TREND = 0.55
    ENTRY_REGIME_CONFIDENCE_FLOOR_SCALP = 0.40
    ENTRY_MAX_BASE_POSITION_PCT = 1.0
    ENTRY_DEGRADED_X_SIZE_MULTIPLIER = 0.5
    ENTRY_PARTIAL_DATA_SIZE_MULTIPLIER = 0.6
    ENTRY_CONTRACT_VERSION = "entry_selector_v1"

    EXIT_ENGINE_FAILCLOSED = True
    EXIT_DEV_SELL_HARD = True
    EXIT_RUG_FLAG_HARD = True
    EXIT_SCALP_STOP_LOSS_PCT = -10
    EXIT_SCALP_RECHECK_SEC = 18
    EXIT_SCALP_MAX_HOLD_SEC = 120
    EXIT_SCALP_BUY_PRESSURE_FLOOR = 0.60
    EXIT_SCALP_LIQUIDITY_DROP_PCT = 20
    EXIT_SCALP_VOLUME_VELOCITY_DECAY = 0.70
    EXIT_SCALP_X_SCORE_DECAY = 0.70
    EXIT_TREND_HARD_STOP_PCT = -18
    EXIT_TREND_PARTIAL1_PCT = 35
    EXIT_TREND_PARTIAL2_PCT = 100
    EXIT_TREND_BUY_PRESSURE_FLOOR = 0.50
    EXIT_TREND_LIQUIDITY_DROP_PCT = 25
    EXIT_CLUSTER_DUMP_HARD = 0.82
    EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD = 0.65
    EXIT_CLUSTER_SELL_CONCENTRATION_WARN = 0.72
    EXIT_CLUSTER_SELL_CONCENTRATION_HARD = 0.78
    EXIT_LIQUIDITY_REFILL_FAIL_MIN = 0.85
    EXIT_SELLER_REENTRY_WEAK_MAX = 0.20
    EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC = 180
    EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD = 2.0
    EXIT_RETRY_MANIPULATION_HARD = 5.0
    EXIT_CREATOR_CLUSTER_RISK_HARD = 0.75
    EXIT_LINKAGE_RISK_HARD = 0.75
    EXIT_CONTRACT_VERSION = "exit_engine_v1"


def get_false_positive_settings() -> FalsePositiveSettings:
    return FalsePositiveSettings()


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


_BASE_PAYLOAD: dict[str, Any] = {
    "token_address": "SoBaseFalsePositive000",
    "symbol": "BASE",
    "name": "Base False Positive",
    "price_usd": 1.0,
    "liquidity_usd": 30000,
    "fast_prescore": 98,
    "age_sec": 120,
    "buy_pressure": 0.86,
    "volume_velocity": 5.4,
    "first30s_buy_ratio": 0.84,
    "bundle_cluster_score": 0.78,
    "priority_fee_avg_first_min": 0.002,
    "pumpfun_to_raydium_sec": 90,
    "holder_entropy_est": 3.2,
    "first50_holder_conc_est": 0.36,
    "x_validation_score": 86,
    "x_validation_delta": 14,
    "x_status": "ok",
    "x_duplicate_text_ratio": 0.15,
    "x_promoter_concentration": 0.18,
    "x_unique_authors_visible": 7,
    "x_contract_mention_presence": 0.8,
    "holder_growth_5m": 40,
    "smart_wallet_hits": 5,
    "top20_holder_share": 0.22,
    "dev_sell_pressure_5m": 0.0,
    "rug_score": 0.08,
    "rug_verdict": "PASS",
    "mint_revoked": True,
    "freeze_revoked": True,
    "lp_burn_confirmed": True,
    "bundle_count_first_60s": 5,
    "bundle_size_value": 18000,
    "unique_wallets_per_bundle_avg": 3.2,
    "bundle_timing_from_liquidity_add_min": 0.65,
    "bundle_success_rate": 0.82,
    "bundle_composition_dominant": "buy-only",
    "bundle_tip_efficiency": 0.75,
    "bundle_failure_retry_pattern": 1.0,
    "cross_block_bundle_correlation": 0.25,
    "bundle_wallet_clustering_score": 0.42,
    "cluster_concentration_ratio": 0.34,
    "num_unique_clusters_first_60s": 4,
    "creator_in_cluster_flag": False,
    "creator_cluster_link_score": 0.10,
    "creator_buyer_link_score": 0.05,
    "dev_buyer_link_score": 0.05,
    "shared_funder_link_score": 0.05,
    "cluster_dev_link_score": 0.05,
    "linkage_risk_score": 0.10,
    "linkage_confidence": 0.80,
    "linkage_reason_codes": [],
    "linkage_metric_origin": "evidence_first",
    "linkage_status": "ok",
    "linkage_warning": None,
    "net_unique_buyers_60s": 9,
    "liquidity_refill_ratio_120s": 1.25,
    "cluster_sell_concentration_120s": 0.30,
    "smart_wallet_dispersion_score": 0.66,
    "x_author_velocity_5m": 1.60,
    "seller_reentry_ratio": 0.42,
    "liquidity_shock_recovery_sec": 52,
    "continuation_status": "ok",
    "continuation_confidence": "high",
    "continuation_coverage_ratio": 1.0,
    "enrichment_status": "ok",
    "rug_status": "ok",
    "wallet_features": {
        "smart_wallet_hits": 5,
        "smart_wallet_tier1_hits": 1,
        "smart_wallet_netflow_bias": 0.25,
    },
}

_BASE_CURRENT: dict[str, Any] = {
    "now_ts": "2026-03-15T12:31:04Z",
    "price_usd_now": 1.02,
    "buy_pressure_now": 0.79,
    "volume_velocity_now": 4.4,
    "liquidity_usd_now": 29200,
    "x_validation_score_now": 69.0,
    "x_status_now": "ok",
    "bundle_cluster_score_now": 0.70,
    "dev_sell_pressure_now": 0.0,
    "rug_flag_now": False,
    "wallet_features": {"smart_wallet_netflow_bias": 0.10},
}

_FALSE_POSITIVE_CASES: dict[str, dict[str, Any]] = {
    "single_cluster_fake_strength": {
        "case_name": "single_cluster_fake_strength",
        "family": "single_cluster_fake_strength",
        "description": "Strong early bundle activity is almost entirely explained by one crowded cluster.",
        "payload_overrides": {
            "token_address": "SoFP001",
            "symbol": "SCFS",
            "name": "Single Cluster Fake Strength",
            "bundle_wallet_clustering_score": 0.96,
            "cluster_concentration_ratio": 0.91,
            "num_unique_clusters_first_60s": 1,
            "bundle_timing_from_liquidity_add_min": 0.22,
            "cross_block_bundle_correlation": 0.71,
            "bundle_success_rate": 0.64,
        },
        "current_overrides": {
            "price_usd_now": 0.93,
            "buy_pressure_now": 0.46,
            "volume_velocity_now": 2.3,
            "liquidity_usd_now": 21500,
            "x_validation_score_now": 61.0,
            "bundle_cluster_score_now": 0.59,
            "cluster_sell_concentration_120s": 0.86,
            "cluster_concentration_ratio_now": 0.88,
            "bundle_composition_dominant_now": "distribution",
            "cross_block_bundle_correlation_now": 0.74,
            "wallet_features": {"smart_wallet_netflow_bias": -0.35},
        },
        "expected_score_signals": {
            "flags_all": ["single_cluster_concentration"],
            "min_fields": {"single_cluster_penalty": 4.0},
            "max_fields": {"organic_multi_cluster_bonus": 2.5},
        },
        "expected_regime_behavior": {
            "entry_decision_not": ["TREND"],
            "blockers_any": [
                "trend_multi_cluster_confirmation_missing",
                "trend_cluster_concentration_high",
            ],
        },
        "expected_exit_behavior": {
            "position_decision": "SCALP",
            "exit_decision": "FULL_EXIT",
            "exit_reason_in": ["cluster_dump_detected"],
            "exit_flags_any": ["cluster_dump_detected"],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "This case should never be interpreted as healthy multi-cluster trend confirmation.",
    },
    "creator_linked_early_buyers": {
        "case_name": "creator_linked_early_buyers",
        "family": "creator_linked_early_buyers",
        "description": "Early buyers look exciting, but linkage evidence ties them back to creator/dev funding.",
        "payload_overrides": {
            "token_address": "SoFP002",
            "symbol": "CLINK",
            "name": "Creator Linked Early Buyers",
            "creator_in_cluster_flag": True,
            "creator_cluster_link_score": 0.89,
            "creator_buyer_link_score": 0.84,
            "dev_buyer_link_score": 0.67,
            "shared_funder_link_score": 0.79,
            "linkage_risk_score": 0.86,
            "linkage_confidence": 0.82,
            "cluster_concentration_ratio": 0.72,
            "num_unique_clusters_first_60s": 2,
        },
        "current_overrides": {
            "buy_pressure_now": 0.69,
            "creator_in_cluster_flag_now": True,
            "creator_cluster_activity_now": 0.88,
            "cluster_concentration_ratio_now": 0.79,
            "cross_block_bundle_correlation_now": 0.86,
            "bundle_composition_dominant_now": "distribution",
            "wallet_features": {"smart_wallet_netflow_bias": -0.28},
            "linkage_risk_score_now": 0.91,
            "creator_buyer_link_score_now": 0.87,
            "shared_funder_link_score_now": 0.82,
        },
        "expected_score_signals": {
            "flags_all": ["creator_cluster_linked", "shared_funder_penalty"],
            "min_fields": {"creator_cluster_penalty": 4.0, "shared_funder_penalty": 1.2},
        },
        "expected_regime_behavior": {
            "entry_decision_not": ["TREND"],
            "blockers_any": ["trend_creator_cluster_linked", "trend_linkage_risk_high"],
        },
        "expected_exit_behavior": {
            "position_decision": "TREND",
            "exit_decision": "FULL_EXIT",
            "exit_reason_in": ["creator_cluster_exit_risk"],
            "exit_flags_any": ["creator_cluster_exit_risk"],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "Linkage risk should stay visible even when raw momentum looks attractive.",
    },
    "retry_heavy_sniper_loop": {
        "case_name": "retry_heavy_sniper_loop",
        "family": "retry_heavy_sniper_loop",
        "description": "Aggressive bundle retries create misleading early momentum and synchronized manipulation signatures.",
        "payload_overrides": {
            "token_address": "SoFP003",
            "symbol": "RETRY",
            "name": "Retry Heavy Sniper Loop",
            "bundle_failure_retry_pattern": 5.8,
            "cross_block_bundle_correlation": 0.91,
            "bundle_success_rate": 0.31,
            "bundle_timing_from_liquidity_add_min": 0.18,
            "bundle_wallet_clustering_score": 0.77,
            "cluster_concentration_ratio": 0.63,
            "num_unique_clusters_first_60s": 3,
        },
        "current_overrides": {
            "buy_pressure_now": 0.44,
            "volume_velocity_now": 2.1,
            "bundle_failure_retry_pattern_now": 6.4,
            "bundle_failure_retry_delta": 3.2,
            "cross_block_bundle_correlation_now": 0.91,
            "bundle_composition_dominant_now": "distribution",
            "wallet_features": {"smart_wallet_netflow_bias": -0.42},
        },
        "expected_score_signals": {
            "flags_all": ["bundle_retry_pattern_suspicious"],
            "min_fields": {"retry_manipulation_penalty": 4.0},
        },
        "expected_regime_behavior": {
            "entry_decision_not": ["TREND"],
            "blockers_any": ["trend_bundle_retry_pattern_severe", "trend_bundle_success_rate_weak"],
        },
        "expected_exit_behavior": {
            "position_decision": "SCALP",
            "exit_decision": "FULL_EXIT",
            "exit_reason_in": ["retry_manipulation_detected"],
            "exit_flags_any": ["retry_manipulation_detected"],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "Retry/correlation evidence should stop the suite from treating this as healthy aggression.",
    },
    "sell_heavy_bundle_distribution": {
        "case_name": "sell_heavy_bundle_distribution",
        "family": "sell_heavy_bundle_distribution",
        "description": "Bundle activity exists, but its composition and follow-through look distribution-heavy rather than constructive.",
        "payload_overrides": {
            "token_address": "SoFP004",
            "symbol": "SELLH",
            "name": "Sell Heavy Bundle Distribution",
            "bundle_composition_dominant": "sell-heavy",
            "bundle_success_rate": 0.29,
            "cluster_concentration_ratio": 0.74,
            "num_unique_clusters_first_60s": 2,
            "cluster_sell_concentration_120s": 0.77,
            "liquidity_refill_ratio_120s": 0.83,
            "seller_reentry_ratio": 0.16,
            "liquidity_shock_recovery_sec": 205,
            "continuation_confidence": "medium",
        },
        "current_overrides": {
            "buy_pressure_now": 0.47,
            "bundle_composition_dominant_now": "distribution",
            "cluster_sell_concentration_120s": 0.76,
            "cluster_concentration_ratio_now": 0.60,
            "liquidity_refill_ratio_120s": 0.72,
            "seller_reentry_ratio": 0.14,
            "liquidity_shock_recovery_sec": 218,
            "wallet_features": {"smart_wallet_netflow_bias": -0.31},
        },
        "expected_score_signals": {
            "flags_all": ["bundle_sell_heavy"],
            "min_fields": {"bundle_sell_heavy_penalty": 4.0},
        },
        "expected_regime_behavior": {
            "entry_decision_not": ["TREND"],
            "blockers_any": ["trend_cluster_concentration_high", "trend_bundle_success_rate_weak"],
        },
        "expected_exit_behavior": {
            "position_decision": "TREND",
            "exit_decision": "FULL_EXIT",
            "exit_reason_in": ["cluster_distribution_exit", "scalp_buy_pressure_breakdown"],
            "exit_warnings_any": ["cluster_distribution_detected"],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "Sell-heavy bundles should not get the same treatment as constructive accumulation.",
    },
    "fake_trend_weak_continuation": {
        "case_name": "fake_trend_weak_continuation",
        "family": "fake_trend_weak_continuation",
        "description": "Early metrics look decent, but continuation evidence is weak and recovery quality is poor.",
        "payload_overrides": {
            "token_address": "SoFP005",
            "symbol": "WKTRD",
            "name": "Fake Trend Weak Continuation",
            "fast_prescore": 77,
            "x_validation_score": 66,
            "x_validation_delta": 3,
            "holder_growth_5m": 21,
            "smart_wallet_hits": 2,
            "net_unique_buyers_60s": 1,
            "liquidity_refill_ratio_120s": 0.72,
            "cluster_sell_concentration_120s": 0.74,
            "smart_wallet_dispersion_score": 0.24,
            "x_author_velocity_5m": 0.18,
            "seller_reentry_ratio": 0.09,
            "liquidity_shock_recovery_sec": 240,
            "continuation_confidence": "low",
            "continuation_status": "partial",
            "continuation_coverage_ratio": 0.57,
            "cluster_concentration_ratio": 0.58,
            "num_unique_clusters_first_60s": 3,
            "bundle_success_rate": 0.48,
            "bundle_wallet_clustering_score": 0.61,
        },
        "current_overrides": {
            "buy_pressure_now": 0.55,
            "cluster_sell_concentration_120s": 0.74,
            "liquidity_refill_ratio_120s": 0.62,
            "seller_reentry_ratio": 0.10,
            "liquidity_shock_recovery_sec": 226,
            "net_unique_buyers_60s": -1,
            "smart_wallet_dispersion_score": 0.20,
            "x_author_velocity_5m": 0.14,
            "wallet_features": {"smart_wallet_netflow_bias": -0.12},
        },
        "expected_score_signals": {
            "flags_all": ["cluster_distribution_risk"],
            "warnings_all": ["continuation_status=partial", "continuation_confidence_low"],
            "min_fields": {"cluster_distribution_risk_penalty": 1.25},
        },
        "expected_regime_behavior": {
            "entry_decision_not": ["TREND"],
            "blockers_any": ["trend_cluster_concentration_high"],
        },
        "expected_exit_behavior": {
            "position_decision": "TREND",
            "exit_decision": "FULL_EXIT",
            "exit_reason_in": ["failed_liquidity_refill_exit"],
            "exit_warnings_any": [
                "failed_liquidity_refill_detected",
                "shock_not_recovered_detected",
            ],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "This case is intentionally honest that continuation weakness is most visible in score/exit/replay layers today.",
    },
    "degraded_x_ambiguous_onchain": {
        "case_name": "degraded_x_ambiguous_onchain",
        "family": "degraded_x_ambiguous_onchain",
        "description": "On-chain data tempts promotion, but degraded X should keep the engine from acting overconfident.",
        "payload_overrides": {
            "token_address": "SoFP006",
            "symbol": "DEGX",
            "name": "Degraded X Ambiguous Onchain",
            "x_status": "degraded",
            "x_validation_score": 52,
            "x_validation_delta": -2,
            "fast_prescore": 84,
            "holder_growth_5m": 24,
            "smart_wallet_hits": 5,
            "continuation_confidence": "medium",
            "continuation_coverage_ratio": 0.78,
        },
        "expected_score_signals": {
            "flags_all": ["x_degraded"],
            "warnings_all": ["x_status=degraded"],
            "regime_candidate": "WATCHLIST",
        },
        "expected_regime_behavior": {
            "entry_decision": "IGNORE",
            "warnings_any": ["x_status_degraded"],
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "Current routing downgrades degraded-X candidates before regime logic can treat them as healthy trend confirmations.",
    },
    "partial_evidence_false_confidence": {
        "case_name": "partial_evidence_false_confidence",
        "family": "partial_evidence_false_confidence",
        "description": "Enough fields are present to look tempting, but missing cluster/rug/enrichment evidence should prevent confident promotion.",
        "payload_overrides": {
            "token_address": "SoFP007",
            "symbol": "PARTL",
            "name": "Partial Evidence False Confidence",
            "enrichment_status": "partial",
            "rug_status": "partial",
            "continuation_status": "partial",
            "continuation_confidence": "low",
            "continuation_coverage_ratio": 0.42,
            "holder_growth_5m": None,
            "smart_wallet_hits": None,
            "bundle_count_first_60s": None,
            "unique_wallets_per_bundle_avg": None,
            "cluster_concentration_ratio": None,
            "num_unique_clusters_first_60s": None,
            "creator_in_cluster_flag": None,
            "linkage_confidence": 0.0,
            "linkage_status": "partial",
        },
        "expected_score_signals": {
            "flags_all": ["enrichment_partial", "rug_partial"],
            "warnings_all": [
                "continuation_status=partial",
                "continuation_confidence_low",
            ],
            "regime_candidate": "WATCHLIST",
        },
        "expected_regime_behavior": {
            "entry_decision": "IGNORE",
        },
        "expected_replay_behavior": {"replay_label": "blocked_no_entry"},
        "notes": "Partial-data caution should remain explicit instead of silently defaulting to confidence.",
    },
}


def list_false_positive_cases() -> list[str]:
    return sorted(_FALSE_POSITIVE_CASES.keys())


def get_false_positive_case(name: str) -> dict[str, Any]:
    if name not in _FALSE_POSITIVE_CASES:
        raise KeyError(f"Unknown false-positive case: {name}")
    case = copy.deepcopy(_FALSE_POSITIVE_CASES[name])
    case["payload"] = build_false_positive_case_payload(name)
    case["current_state"] = build_false_positive_case_current(name)
    return case


def build_false_positive_case_payload(name: str) -> dict[str, Any]:
    case = _FALSE_POSITIVE_CASES[name]
    return _deep_merge(_BASE_PAYLOAD, case.get("payload_overrides", {}))


def build_false_positive_case_current(name: str) -> dict[str, Any]:
    case = _FALSE_POSITIVE_CASES[name]
    return _deep_merge(_BASE_CURRENT, case.get("current_overrides", {}))


def validate_false_positive_case(case: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for key in (
        "case_name",
        "description",
        "expected_score_signals",
        "expected_regime_behavior",
        "expected_replay_behavior",
        "notes",
    ):
        if key not in case:
            warnings.append(f"missing_key:{key}")
    payload = case.get("payload") or {}
    for field in ("token_address", "symbol", "name", "fast_prescore", "rug_score", "rug_verdict"):
        if payload.get(field) is None:
            warnings.append(f"payload_missing:{field}")
    return warnings


def score_false_positive_case(name: str, settings: FalsePositiveSettings | None = None) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    payload = build_false_positive_case_payload(name)
    return score_token(payload, settings)


def build_false_positive_entry_input(
    name: str,
    *,
    scored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_false_positive_case_payload(name)
    scored = scored or score_false_positive_case(name)
    merged = copy.deepcopy(payload)
    merged.update(copy.deepcopy(scored))
    return merged


def evaluate_false_positive_entry(
    name: str,
    settings: FalsePositiveSettings | None = None,
    *,
    scored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    entry_input = build_false_positive_entry_input(name, scored=scored)
    return decide_entry(entry_input, settings)


def build_false_positive_position(
    name: str,
    *,
    settings: FalsePositiveSettings | None = None,
    entry_result: dict[str, Any] | None = None,
    forced_entry_decision: str | None = None,
    scored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    scored = scored or score_false_positive_case(name, settings)
    payload = build_false_positive_case_payload(name)
    merged = copy.deepcopy(payload)
    merged.update(copy.deepcopy(scored))

    expected_exit = _FALSE_POSITIVE_CASES[name].get("expected_exit_behavior", {})
    decision = forced_entry_decision or (entry_result or {}).get("entry_decision") or expected_exit.get("position_decision") or "TREND"
    entry_snapshot = (entry_result or {}).get("entry_snapshot") or build_entry_snapshot(merged)
    return {
        "position_id": f"{name}-position",
        "token_address": merged.get("token_address"),
        "symbol": merged.get("symbol"),
        "entry_decision": str(decision).upper(),
        "entry_time": "2026-03-15T12:30:41Z",
        "entry_price_usd": float(merged.get("price_usd") or 1.0),
        "entry_snapshot": entry_snapshot,
        "partials_taken": [],
    }


def evaluate_false_positive_exit(
    name: str,
    settings: FalsePositiveSettings | None = None,
    *,
    entry_result: dict[str, Any] | None = None,
    forced_entry_decision: str | None = None,
    scored: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    current = build_false_positive_case_current(name)
    position = build_false_positive_position(
        name,
        settings=settings,
        entry_result=entry_result,
        forced_entry_decision=forced_entry_decision,
        scored=scored,
    )
    return decide_exit(position, current, settings)


def replay_false_positive_case(name: str, settings: FalsePositiveSettings | None = None) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    scored = score_false_positive_case(name, settings)
    entry = evaluate_false_positive_entry(name, settings, scored=scored)

    replay: dict[str, Any] = {
        "case_name": name,
        "scored": scored,
        "entry": entry,
        "replayed_at": utc_now_iso(),
    }
    if entry["entry_decision"] == "IGNORE":
        replay["exit"] = None
        replay["replay_label"] = "blocked_no_entry"
        replay["replay_reason"] = entry.get("entry_reason") or "blocked"
        return replay

    exit_result = evaluate_false_positive_exit(name, settings, entry_result=entry, scored=scored)
    replay["exit"] = exit_result
    replay["replay_reason"] = exit_result.get("exit_reason") or "hold_conditions_intact"
    if exit_result["exit_decision"] == "FULL_EXIT":
        replay["replay_label"] = "protective_full_exit"
    elif exit_result["exit_decision"] == "PARTIAL_EXIT":
        replay["replay_label"] = "partial_resolution"
    elif entry["entry_decision"] == "SCALP":
        replay["replay_label"] = "low_confidence_scalp_only"
    else:
        replay["replay_label"] = "trend_survived"
    return replay


def build_false_positive_smoke_summary(
    settings: FalsePositiveSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_false_positive_settings()
    cases_out: list[dict[str, Any]] = []
    validation_warnings: list[str] = []

    for name in list_false_positive_cases():
        case = get_false_positive_case(name)
        validation_warnings.extend([f"{name}:{warning}" for warning in validate_false_positive_case(case)])
        replay = replay_false_positive_case(name, settings)
        cases_out.append(
            {
                "case_name": name,
                "family": case["family"],
                "score_regime_candidate": replay["scored"]["regime_candidate"],
                "entry_decision": replay["entry"]["entry_decision"],
                "replay_label": replay["replay_label"],
                "exit_reason": (replay.get("exit") or {}).get("exit_reason"),
            }
        )

    status = "ok" if not validation_warnings else "warning"
    families = sorted({item["family"] for item in cases_out})
    return {
        "contract_version": "false_positive_fixture_suite.v1",
        "generated_at": utc_now_iso(),
        "total_cases": len(cases_out),
        "case_names": [item["case_name"] for item in cases_out],
        "failure_mode_families": families,
        "status": status,
        "validation_warnings": validation_warnings,
        "cases": cases_out,
    }


def render_false_positive_summary_md(summary: dict[str, Any]) -> str:
    lines = [
        "# False-positive fixture suite smoke summary",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- total_cases: `{summary['total_cases']}`",
        f"- status: `{summary['status']}`",
        "",
        "## Covered families",
        "",
    ]
    for family in summary.get("failure_mode_families", []):
        lines.append(f"- `{family}`")
    lines.extend(["", "## Case results", ""])
    for case in summary.get("cases", []):
        lines.append(
            f"- `{case['case_name']}` → score_route=`{case['score_regime_candidate']}`, "
            f"entry=`{case['entry_decision']}`, replay=`{case['replay_label']}`, "
            f"exit_reason=`{case.get('exit_reason')}`"
        )
    if summary.get("validation_warnings"):
        lines.extend(["", "## Validation warnings", ""])
        for warning in summary["validation_warnings"]:
            lines.append(f"- `{warning}`")
    return "\n".join(lines) + "\n"
