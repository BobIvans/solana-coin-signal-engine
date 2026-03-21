"""Feature grouping helpers for offline feature importance analysis."""

from __future__ import annotations

from collections.abc import Iterable

FEATURE_GROUP_PATTERNS: dict[str, tuple[str, ...]] = {
    "bundle_features": (
        "bundle_",
        "cross_block_bundle_",
        "unique_wallets_per_bundle_",
    ),
    "cluster_features": (
        "cluster_",
        "creator_cluster_",
        "creator_in_cluster_",
        "num_unique_clusters_",
        "organic_multi_cluster_",
        "single_cluster_",
    ),
    "linkage_features": (
        "linkage_",
        "creator_dev_link_",
        "creator_buyer_link_",
        "dev_buyer_link_",
        "shared_funder_",
        "funder_overlap_",
        "cluster_dev_link_",
        "creator_cluster_link_",
    ),
    "continuation_features": (
        "continuation_",
        "net_unique_buyers_",
        "liquidity_refill_",
        "seller_reentry_",
        "liquidity_shock_",
        "smart_wallet_dispersion_",
    ),
    "wallet_features": (
        "wallet_",
        "smart_wallet_",
        "holder_",
    ),
    "x_features": (
        "x_",
    ),
    "regime_features": (
        "regime_",
        "expected_hold_",
        "final_score",
        "onchain_core",
        "early_signal_bonus",
        "x_validation_bonus",
        "rug_penalty",
        "spam_penalty",
        "confidence_adjustment",
        "wallet_adjustment",
    ),
    "evidence_quality_features": (
        "evidence_",
        "partial_evidence_",
        "low_confidence_evidence_",
        "sizing_",
    ),
    "friction_features": (
        "slippage_",
        "priority_fee_",
        "liquidity_usd",
        "buy_pressure_",
        "volume_velocity_",
    ),
    "meta_features": (
        "run_id",
        "ts",
        "token_address",
        "pair_address",
        "symbol",
        "config_hash",
        "position_id",
        "schema_version",
        "dry_run",
        "synthetic_trade_flag",
        "decision",
        "entry_decision",
        "replay_input_origin",
        "replay_data_status",
        "replay_resolution_status",
    ),
}

_TARGET_FIELDS = {
    "profitable_trade_flag",
    "trend_success_flag",
    "fast_failure_flag",
}

_OUTCOME_ONLY_FIELDS = {
    "net_pnl_pct",
    "gross_pnl_pct",
    "hold_sec",
    "exit_reason_final",
    "mfe_pct",
    "mae_pct",
    "mfe_pct_240s",
    "mae_pct_240s",
    "trend_survival_15m",
    "trend_survival_60m",
    "time_to_first_profit_sec",
    "exit_decision",
    "exit_flags",
    "exit_warnings",
}

_OUTCOME_PREFIXES = (
    "mfe_pct",
    "mae_pct",
    "trend_survival_",
    "time_to_first_profit_",
    "exit_",
)


def feature_group_for_name(feature_name: str) -> str:
    if feature_name in _TARGET_FIELDS:
        return "meta_features"
    if feature_name in _OUTCOME_ONLY_FIELDS or any(feature_name.startswith(prefix) for prefix in _OUTCOME_PREFIXES):
        return "outcome_only_fields"
    for group_name, patterns in FEATURE_GROUP_PATTERNS.items():
        for pattern in patterns:
            if feature_name == pattern or feature_name.startswith(pattern):
                return group_name
    return "uncategorized_features"


def group_features(feature_names: Iterable[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for feature_name in feature_names:
        grouped.setdefault(feature_group_for_name(feature_name), []).append(feature_name)
    return {group_name: sorted(names) for group_name, names in sorted(grouped.items())}
