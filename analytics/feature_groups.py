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
    ),
    "exit_features": (
        "exit_",
        "hold_sec",
        "time_to_first_profit_sec",
        "mfe_pct",
        "mae_pct",
        "trend_survival_",
    ),
    "risk_features": (
        "rug_",
        "linkage_",
        "creator_dev_link_",
        "creator_buyer_link_",
        "dev_buyer_link_",
        "shared_funder_",
        "funder_overlap_",
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
    ),
}

_TARGET_FIELDS = {
    "profitable_trade_flag",
    "trend_success_flag",
    "fast_failure_flag",
}


def feature_group_for_name(feature_name: str) -> str:
    for group_name, patterns in FEATURE_GROUP_PATTERNS.items():
        for pattern in patterns:
            if feature_name == pattern or feature_name.startswith(pattern):
                return group_name
    return "meta_features" if feature_name in _TARGET_FIELDS else "uncategorized_features"


def group_features(feature_names: Iterable[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for feature_name in feature_names:
        grouped.setdefault(feature_group_for_name(feature_name), []).append(feature_name)
    return {group_name: sorted(names) for group_name, names in sorted(grouped.items())}
