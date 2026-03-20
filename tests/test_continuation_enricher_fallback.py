from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.continuation_enricher import compute_continuation_metrics


PAIR_CREATED_TS = 1_000


def test_tx_present_x_missing_marks_partial_without_crashing():
    txs = [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 100.0,
            "tokenTransfers": [{"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 5}],
        },
        {
            "timestamp": 1_030,
            "success": True,
            "liquidity_usd": 80.0,
            "tokenTransfers": [{"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 2}],
        },
    ]

    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        txs=txs,
        pair_created_ts=PAIR_CREATED_TS,
    )

    assert result["net_unique_buyers_60s"] == 0
    assert result["x_author_velocity_5m"] is None
    assert result["continuation_status"] == "partial"
    assert result["continuation_warning"] == "continuation_partial_evidence"
    assert result["continuation_inputs_status"]["x"] == "missing"


def test_wallet_registry_missing_does_not_fake_dispersion():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "1970-01-01T00:16:40Z"},
        x_snapshots=[{"x_status": "ok", "cards": [{"author_handle": "@a", "created_at": "1970-01-01T00:16:40Z"}]}],
        wallet_lookup={},
        hit_wallets=["buyer_a", "buyer_b"],
    )

    assert result["smart_wallet_dispersion_score"] is None
    assert result["continuation_inputs_status"]["wallet_registry"] == "missing"
    assert "wallet_registry" in result["continuation_missing_evidence"]


def test_sparse_evidence_overall_stays_low_confidence():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": None},
        txs=[{"timestamp": None, "tokenTransfers": [{"fromUserAccount": None, "toUserAccount": "", "tokenAmount": "bad"}]}],
        x_snapshots=[{"x_status": "ok", "cards": [{"author_handle": "@a"}]}],
        wallet_lookup={"validated_wallets": {"buyer_a": {"wallet": "buyer_a"}}},
        hit_wallets=["buyer_a"],
    )

    assert all(result[field] is None for field in (
        "net_unique_buyers_60s",
        "liquidity_refill_ratio_120s",
        "cluster_sell_concentration_120s",
        "smart_wallet_dispersion_score",
        "x_author_velocity_5m",
        "seller_reentry_ratio",
        "liquidity_shock_recovery_sec",
    ))
    assert result["continuation_status"] == "missing"
    assert result["continuation_confidence"] == "low"


def test_malformed_payloads_degrade_safely_and_emit_warnings():
    result = compute_continuation_metrics(
        token_ctx={"pair_created_at": "not-a-timestamp"},
        txs=[None, {"tokenTransfers": "bad-shape"}],
        x_snapshots=[{"cards": [None, {"author_handle": None, "created_at": "bad-ts"}]}],
        wallet_lookup={"validated_wallets": {"buyer_a": {"wallet": "buyer_a", "tier": None}}},
        hit_wallets=[None, "buyer_a"],
    )

    assert result["continuation_status"] in {"partial", "missing"}
    assert result["continuation_confidence"] == "low"
    assert result["continuation_warning"]
    assert isinstance(result["continuation_warnings"], list)


def test_all_failed_txs_leave_transfer_metrics_unresolved():
    txs = [
        {
            "timestamp": 1_000,
            "success": False,
            "liquidity_usd": 100.0,
            "participants": [{"wallet": "buyer_a", "funder": "shared"}],
            "tokenTransfers": [{"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 10}],
        },
        {
            "timestamp": 1_020,
            "success": False,
            "liquidity_usd": 90.0,
            "tokenTransfers": [{"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 4}],
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
    assert result["continuation_inputs_status"]["tx"] == "ready"
