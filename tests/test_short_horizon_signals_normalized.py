from __future__ import annotations

from analytics.short_horizon_signals import (
    compute_net_unique_buyers_60s,
    compute_seller_reentry_ratio,
)

PAIR_CREATED_TS = 1_000


def test_net_unique_buyers_works_with_normalized_snake_case_only_shape():
    txs = [
        {
            "timestamp": 1_010,
            "success": True,
            "token_transfers": [
                {"from_user_account": "lp_pool", "to_user_account": "buyer_a", "token_amount": 10},
                {"from_user_account": "lp_pool", "to_user_account": "buyer_b", "token_amount": 5},
                {"from_user_account": "seller_a", "to_user_account": "lp_pool", "token_amount": 3},
            ],
        }
    ]
    assert compute_net_unique_buyers_60s(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 1


def test_seller_reentry_ratio_works_with_normalized_snake_case_only_shape():
    txs = [
        {"timestamp": 1_005, "success": True, "token_transfers": [{"from_user_account": "lp_pool", "to_user_account": "buyer_a", "token_amount": 10}]},
        {"timestamp": 1_025, "success": True, "token_transfers": [{"from_user_account": "buyer_a", "to_user_account": "lp_pool", "token_amount": 4}]},
        {"timestamp": 1_035, "success": True, "token_transfers": [{"from_user_account": "lp_pool", "to_user_account": "buyer_a", "token_amount": 6}]},
    ]
    assert compute_seller_reentry_ratio(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 1.0
