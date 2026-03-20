from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.continuation_enricher import build_continuation_payload, compute_continuation_metrics
from analytics.short_horizon_signals import (
    compute_cluster_sell_concentration_120s,
    compute_net_unique_buyers_60s,
    compute_seller_reentry_ratio,
)

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover
    Draft7Validator = None


PAIR_CREATED_TS = 1_000


def _wallet_lookup() -> dict:
    return {
        "validated_wallets": {
            "buyer_a": {"wallet": "buyer_a", "tier": "tier_1", "family_id": "fam_a", "cluster_id": "cluster_a"},
            "buyer_b": {"wallet": "buyer_b", "tier": "tier_2", "family_id": "fam_b", "cluster_id": "cluster_b"},
            "buyer_c": {"wallet": "buyer_c", "tier": "tier_3", "family_id": "fam_c", "cluster_id": "cluster_c"},
        }
    }


def _organic_txs() -> list[dict]:
    return [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 100.0,
            "participants": [
                {"wallet": "buyer_a", "funder": "shared_a"},
                {"wallet": "buyer_b", "funder": "shared_a"},
                {"wallet": "buyer_c", "funder": "shared_c"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_c", "tokenAmount": 5},
            ],
        },
        {
            "timestamp": 1_025,
            "success": True,
            "liquidity_usd": 60.0,
            "tokenTransfers": [
                {"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 18},
                {"fromUserAccount": "buyer_b", "toUserAccount": "lp_pool", "tokenAmount": 12},
            ],
        },
        {
            "timestamp": 1_050,
            "success": True,
            "liquidity_usd": 100.0,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 4},
            ],
        },
    ]


def _distribution_txs() -> list[dict]:
    return [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 120.0,
            "participants": [
                {"wallet": "seller_a", "funder": "shared_a"},
                {"wallet": "seller_b", "funder": "shared_a"},
                {"wallet": "seller_c", "funder": "shared_a"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 4},
            ],
        },
        {
            "timestamp": 1_020,
            "success": True,
            "liquidity_usd": 45.0,
            "tokenTransfers": [
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 20},
                {"fromUserAccount": "seller_b", "toUserAccount": "lp_pool", "tokenAmount": 18},
                {"fromUserAccount": "seller_c", "toUserAccount": "lp_pool", "tokenAmount": 14},
            ],
        },
        {
            "timestamp": 1_090,
            "success": True,
            "liquidity_usd": 65.0,
            "tokenTransfers": [
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 8},
            ],
        },
    ]


def _x_snapshots() -> list[dict]:
    return [{
        "x_status": "ok",
        "cards": [
            {"author_handle": "@alpha", "created_at": "1970-01-01T00:16:40Z"},
            {"author_handle": "@beta", "created_at": "1970-01-01T00:18:20Z"},
            {"author_handle": "@gamma", "created_at": "1970-01-01T00:20:00Z"},
        ],
    }]


def test_mixed_evidence_produces_full_continuation_payload():
    result = compute_continuation_metrics(
        token_ctx={"token_address": "mint1", "pair_address": "pair1", "pair_created_at": "1970-01-01T00:16:40Z", "creator_wallet": "creator1"},
        txs=_organic_txs(),
        x_snapshots=_x_snapshots(),
        wallet_lookup=_wallet_lookup(),
        hit_wallets=["buyer_a", "buyer_b", "buyer_c"],
        pair_created_ts=PAIR_CREATED_TS,
        creator_wallet="creator1",
    )

    assert result["net_unique_buyers_60s"] == 1
    assert result["liquidity_refill_ratio_120s"] == 1.0
    assert result["cluster_sell_concentration_120s"] == 1.0
    assert result["seller_reentry_ratio"] == 0.5
    assert result["liquidity_shock_recovery_sec"] == 25
    assert result["smart_wallet_dispersion_score"] == 0.666667
    assert result["x_author_velocity_5m"] == 0.6
    assert result["continuation_status"] == "complete"
    assert result["continuation_confidence"] == "high"
    assert result["continuation_metric_origin"] == "mixed_evidence"
    assert result["continuation_coverage_ratio"] == 1.0


def test_tx_only_fake_trend_stays_partial_and_does_not_claim_social_or_wallet_support():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        txs=_distribution_txs(),
        pair_created_ts=PAIR_CREATED_TS,
    )

    assert result["cluster_sell_concentration_120s"] == 1.0
    assert result["liquidity_refill_ratio_120s"] == 0.266667
    assert result["seller_reentry_ratio"] is None
    assert result["smart_wallet_dispersion_score"] is None
    assert result["x_author_velocity_5m"] is None
    assert result["continuation_status"] == "partial"
    assert result["continuation_metric_origin"] == "computed_from_tx"
    assert result["continuation_confidence"] in {"medium", "low"}
    assert "wallet_registry" in result["continuation_missing_evidence"]
    assert "x" in result["continuation_missing_evidence"]


def test_x_only_evidence_is_supported_without_fabricating_tx_metrics():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        x_snapshots=_x_snapshots(),
    )

    assert result["x_author_velocity_5m"] == 0.6
    assert result["net_unique_buyers_60s"] is None
    assert result["smart_wallet_dispersion_score"] is None
    assert result["continuation_status"] == "partial"
    assert result["continuation_metric_origin"] == "computed_from_x"
    assert result["continuation_inputs_status"]["x"] == "ready"


def test_wallet_only_evidence_produces_dispersion_with_honest_partial_status():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        wallet_lookup=_wallet_lookup(),
        hit_wallets=["buyer_a", "buyer_b", "buyer_c"],
    )

    assert result["smart_wallet_dispersion_score"] == 0.666667
    assert result["x_author_velocity_5m"] is None
    assert result["net_unique_buyers_60s"] is None
    assert result["continuation_status"] == "partial"
    assert result["continuation_metric_origin"] == "computed_from_wallet_registry"


def test_build_payload_matches_schema_when_available():
    payload = build_continuation_payload(
        token_ctx={"token_address": "mint1", "pair_address": "pair1", "pair_created_at": "1970-01-01T00:16:40Z"},
        txs=_organic_txs(),
        x_snapshots=_x_snapshots(),
        wallet_lookup=_wallet_lookup(),
        hit_wallets=["buyer_a", "buyer_b", "buyer_c"],
    )

    assert payload["provenance"]["continuation_status"] == "complete"
    assert payload["continuation_metrics"]["x_author_velocity_5m"] == 0.6

    if Draft7Validator is not None:
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "continuation_enrichment.schema.json").read_text())
        Draft7Validator(schema).validate(payload)


def test_failed_txs_do_not_fake_continuation_strength():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 100.0,
            "participants": [
                {"wallet": "buyer_a", "funder": "shared_a"},
                {"wallet": "buyer_b", "funder": "shared_a"},
                {"wallet": "buyer_c", "funder": "shared_c"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_c", "tokenAmount": 5},
            ],
        },
        {
            "timestamp": 1_025,
            "success": True,
            "liquidity_usd": 60.0,
            "tokenTransfers": [
                {"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 18},
                {"fromUserAccount": "buyer_b", "toUserAccount": "lp_pool", "tokenAmount": 12},
            ],
        },
        {
            "timestamp": 1_050,
            "success": True,
            "liquidity_usd": 100.0,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 4},
            ],
        },
        {
            "timestamp": 1_015,
            "success": False,
            "participants": [
                {"wallet": "fake_seller_a", "funder": "shared_fake"},
                {"wallet": "fake_seller_b", "funder": "shared_fake"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "fake_buyer_a", "tokenAmount": 500},
                {"fromUserAccount": "lp_pool", "toUserAccount": "fake_buyer_b", "tokenAmount": 400},
                {"fromUserAccount": "fake_seller_a", "toUserAccount": "lp_pool", "tokenAmount": 900},
                {"fromUserAccount": "fake_seller_b", "toUserAccount": "lp_pool", "tokenAmount": 850},
            ],
        },
        {
            "timestamp": 1_055,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "unknown_buyer", "tokenAmount": 777},
            ],
        },
    ]

    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        txs=txs,
        pair_created_ts=PAIR_CREATED_TS,
    )

    assert result["net_unique_buyers_60s"] == 1
    assert result["cluster_sell_concentration_120s"] == 1.0
    assert result["seller_reentry_ratio"] == 0.5
    assert result["continuation_status"] == "partial"
    assert result["continuation_metric_origin"] == "computed_from_tx"


def test_lp_and_router_contamination_do_not_inflate_net_unique_buyers():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 100.0,
            "participants": [
                {"wallet": "organic_a", "funder": "shared_a"},
                {"wallet": "organic_b", "funder": "shared_b"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "organic_a", "tokenAmount": 7},
                {"fromUserAccount": "lp_pool", "toUserAccount": "organic_b", "tokenAmount": 6},
                {"fromUserAccount": "router_vault", "toUserAccount": "fee_vault", "tokenAmount": 99},
                {"fromUserAccount": "system_program", "toUserAccount": "amm_pool", "tokenAmount": 50},
            ],
        },
        {
            "timestamp": 1_020,
            "success": True,
            "liquidity_usd": 70.0,
            "tokenTransfers": [
                {"fromUserAccount": "organic_a", "toUserAccount": "lp_pool", "tokenAmount": 5},
            ],
        },
    ]

    assert compute_net_unique_buyers_60s(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 1


def test_technical_churn_does_not_create_fake_seller_reentry():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 110.0,
            "participants": [
                {"wallet": "organic_a", "funder": "shared_a"},
                {"wallet": "organic_b", "funder": "shared_b"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "organic_a", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "organic_b", "tokenAmount": 5},
            ],
        },
        {
            "timestamp": 1_020,
            "success": True,
            "liquidity_usd": 70.0,
            "tokenTransfers": [
                {"fromUserAccount": "organic_a", "toUserAccount": "lp_pool", "tokenAmount": 6},
            ],
        },
        {
            "timestamp": 1_050,
            "success": True,
            "liquidity_usd": 71.0,
            "tokenTransfers": [
                {"fromUserAccount": "organic_a", "toUserAccount": "router_vault", "tokenAmount": 2},
                {"fromUserAccount": "router_vault", "toUserAccount": "organic_a", "tokenAmount": 2},
            ],
        },
    ]

    assert compute_seller_reentry_ratio(pair_created_ts=PAIR_CREATED_TS, txs=txs) == 0.0


def test_ambiguous_participants_do_not_inflate_continuation_strength_and_stay_partial():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 120.0,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "unknown_buyer", "tokenAmount": 10},
                {"fromUserAccount": "unknown_seller", "toUserAccount": "lp_pool", "tokenAmount": 7},
            ],
        },
        {
            "timestamp": 1_030,
            "success": True,
            "liquidity_usd": 75.0,
            "tokenTransfers": [
                {"fromUserAccount": "router_vault", "toUserAccount": "unknown_buyer", "tokenAmount": 4},
                {"fromUserAccount": "unknown_buyer", "toUserAccount": "router_vault", "tokenAmount": 4},
            ],
        },
        {
            "timestamp": 1_060,
            "success": True,
            "liquidity_usd": 90.0,
            "tokenTransfers": [
                {"fromUserAccount": "system_program", "toUserAccount": "amm_pool", "tokenAmount": 50},
            ],
        },
    ]

    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        txs=txs,
        pair_created_ts=PAIR_CREATED_TS,
    )

    assert result["net_unique_buyers_60s"] is None
    assert result["cluster_sell_concentration_120s"] is None
    assert result["seller_reentry_ratio"] is None
    assert result["continuation_status"] == "partial"
    assert result["continuation_inputs_status"]["tx"] == "partial"
    assert "tx_continuation_metrics_partially_resolved" in result["continuation_warnings"]


def test_cluster_sell_concentration_ignores_technical_sell_actors():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 120.0,
            "participants": [
                {"wallet": "seller_a", "funder": "shared_a"},
                {"wallet": "seller_b", "funder": "shared_a"},
                {"wallet": "seller_c", "funder": "shared_a"},
            ],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "seller_a", "tokenAmount": 4},
            ],
        },
        {
            "timestamp": 1_020,
            "success": True,
            "liquidity_usd": 45.0,
            "tokenTransfers": [
                {"fromUserAccount": "seller_a", "toUserAccount": "lp_pool", "tokenAmount": 20},
                {"fromUserAccount": "seller_b", "toUserAccount": "lp_pool", "tokenAmount": 18},
                {"fromUserAccount": "seller_c", "toUserAccount": "lp_pool", "tokenAmount": 14},
                {"fromUserAccount": "lp_pool", "toUserAccount": "router_vault", "tokenAmount": 1000},
                {"fromUserAccount": "amm_pool", "toUserAccount": "system_program", "tokenAmount": 900},
            ],
        },
    ]

    assert compute_cluster_sell_concentration_120s(
        pair_created_ts=PAIR_CREATED_TS,
        txs=txs,
        creator_wallet="creator1",
    ) == 1.0
