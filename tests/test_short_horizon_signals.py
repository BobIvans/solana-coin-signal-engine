from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.short_horizon_signals import (
    compute_cluster_sell_concentration_120s,
    compute_liquidity_refill_ratio_120s,
    compute_liquidity_shock_recovery_sec,
    compute_net_unique_buyers_60s,
    compute_seller_reentry_ratio,
    compute_smart_wallet_dispersion_score,
    compute_x_author_velocity_5m,
)


PAIR_CREATED_TS = 1_000


def test_compute_net_unique_buyers_60s_counts_distinct_buyers_minus_sellers():
    txs = [
        {
            "timestamp": 1_010,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 10},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 5},
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 3},
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 1},
            ],
        }
    ]

    assert compute_net_unique_buyers_60s(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 1
    assert compute_net_unique_buyers_60s(pair_created_ts=PAIR_CREATED_TS, txs=[{"timestamp": 1_010}]) is None


def test_compute_liquidity_refill_ratio_120s_uses_baseline_shock_and_recovery():
    txs = [
        {"timestamp": 1_000, "liquidity_usd": 100.0},
        {"timestamp": 1_040, "liquidity_usd": 60.0},
        {"timestamp": 1_100, "liquidity_usd": 90.0},
    ]

    assert compute_liquidity_refill_ratio_120s(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 0.75


def test_compute_cluster_sell_concentration_120s_requires_cluster_evidence():
    txs_with_clusters = [
        {
            "timestamp": 1_005,
            "participants": [
                {"wallet": "seller_a", "funder": "shared"},
                {"wallet": "seller_b", "funder": "shared"},
                {"wallet": "seller_c", "funder": "other"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 40},
                {"fromUserAccount": "seller_b", "toUserAccount": "lp_pool", "tokenAmount": 20},
                {"fromUserAccount": "seller_c", "toUserAccount": "lp_pool", "tokenAmount": 10},
            ],
        }
    ]

    assert compute_cluster_sell_concentration_120s(pair_created_ts=PAIR_CREATED_TS, txs=txs_with_clusters) == 0.857143
    assert compute_cluster_sell_concentration_120s(pair_created_ts=PAIR_CREATED_TS, txs=[{"timestamp": 1_005, "tokenTransfers": txs_with_clusters[0]["tokenTransfers"]}]) is None


def test_compute_smart_wallet_dispersion_score_rewards_family_diversity():
    lookup = {
        "validated_wallets": {
            "w1": {"wallet": "w1", "tier": "tier_1", "status": "active", "family_id": "fam_a", "cluster_id": "cluster_1"},
            "w2": {"wallet": "w2", "tier": "tier_2", "status": "active", "family_id": "fam_b", "cluster_id": "cluster_2"},
            "w3": {"wallet": "w3", "tier": "tier_3", "status": "watch", "family_id": "fam_c", "cluster_id": "cluster_3"},
        }
    }
    concentrated_lookup = {
        "validated_wallets": {
            "w1": {"wallet": "w1", "tier": "tier_1", "status": "active", "family_id": "fam_a", "cluster_id": "cluster_1"},
            "w2": {"wallet": "w2", "tier": "tier_1", "status": "active", "family_id": "fam_a", "cluster_id": "cluster_1"},
            "w3": {"wallet": "w3", "tier": "tier_1", "status": "active", "family_id": "fam_a", "cluster_id": "cluster_1"},
        }
    }

    diversified = compute_smart_wallet_dispersion_score(["w1", "w2", "w3"], lookup)
    concentrated = compute_smart_wallet_dispersion_score(["w1", "w2", "w3"], concentrated_lookup)

    assert diversified == 0.666667
    assert concentrated == 0.0
    assert compute_smart_wallet_dispersion_score(["unknown"], lookup) is None


def test_compute_x_author_velocity_5m_counts_new_authors_per_minute():
    snapshots = [
        {
            "cards": [
                {"author_handle": "@a", "created_at": "1970-01-01T00:16:40Z"},
                {"author_handle": "@b", "created_at": "1970-01-01T00:18:20Z"},
                {"author_handle": "@c", "created_at": "1970-01-01T00:21:00Z"},
                {"author_handle": "@d", "created_at": "1970-01-01T00:22:01Z"},
            ]
        }
    ]

    assert compute_x_author_velocity_5m(snapshots) == 0.6
    assert compute_x_author_velocity_5m([{"cards": [{"author_handle": "@a"}]}]) is None


def test_compute_seller_reentry_ratio_requires_sell_then_rebuy_lifecycle():
    txs = [
        {"timestamp": 1_005, "tokenTransfers": [{"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 10}]},
        {"timestamp": 1_015, "tokenTransfers": [{"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 8}]},
        {"timestamp": 1_025, "tokenTransfers": [{"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 4}]},
        {"timestamp": 1_035, "tokenTransfers": [{"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 6}]},
        {"timestamp": 1_045, "tokenTransfers": [{"fromUserAccount": "buyer_b", "toUserAccount": "lp_pool", "tokenAmount": 4}]},
    ]

    assert compute_seller_reentry_ratio(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 0.5
    assert compute_seller_reentry_ratio(pair_created_ts=PAIR_CREATED_TS, txs=[{"timestamp": 1_010}]) is None


def test_compute_liquidity_shock_recovery_sec_requires_honest_recovery():
    txs = [
        {"timestamp": 1_000, "liquidity_usd": 100.0},
        {"timestamp": 1_030, "liquidity_usd": 80.0},
        {"timestamp": 1_090, "liquidity_usd": 100.0},
    ]
    unrecovered = [
        {"timestamp": 1_000, "liquidity_usd": 100.0},
        {"timestamp": 1_030, "liquidity_usd": 70.0},
        {"timestamp": 1_090, "liquidity_usd": 92.0},
    ]

    assert compute_liquidity_shock_recovery_sec(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 60
    assert compute_liquidity_shock_recovery_sec(pair_created_ts=PAIR_CREATED_TS, txs=unrecovered) is None
