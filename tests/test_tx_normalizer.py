from __future__ import annotations

from data.tx_normalizer import normalize_tx_batch


def test_normalize_tx_batch_preserves_useful_fields_and_contract_metadata():
    batch = normalize_tx_batch(
        [
            {
                "signature": "sig-1",
                "timestamp": 1_710_000_000,
                "slot": 101,
                "feePayer": "payer-1",
                "nativeTransfers": [{"fromUserAccount": "payer-1", "toUserAccount": "lp-1", "amount": 1000000000}],
                "tokenTransfers": [{"fromUserAccount": "lp-1", "toUserAccount": "buyer-1", "tokenAmount": 12.5, "mint": "mint-1"}],
                "success": True,
                "liquidity_usd": 1234.5,
            }
        ],
        source_provider="helius",
        lookup_key="pair-1",
        lookup_type="pair_address",
    )

    assert batch["contract_version"] == "tx_batch.v1"
    assert batch["tx_batch_status"] == "usable"
    assert batch["tx_batch_record_count"] == 1
    record = batch["tx_records"][0]
    assert record["signature"] == "sig-1"
    assert record["pair_address"] == "pair-1"
    assert record["feePayer"] == "payer-1"
    assert record["blockTime"] == 1_710_000_000
    assert record["tokenTransfers"][0]["mint"] == "mint-1"


def test_partial_batch_with_missing_optionals_stays_loadable_without_fabrication():
    batch = normalize_tx_batch(
        [{"signature": "sig-2", "slot": 102, "err": None}],
        source_provider="solana_rpc",
        lookup_key="wallet-1",
        lookup_type="address",
    )

    assert batch["tx_batch_status"] == "partial"
    record = batch["tx_records"][0]
    assert record["signature"] == "sig-2"
    assert record["timestamp"] is None
    assert record["tokenTransfers"] == []
    assert record["nativeTransfers"] == []


def test_malformed_entries_are_not_fabricated_into_valid_transactions():
    batch = normalize_tx_batch(
        [None, {"timestamp": "bad-ts"}],
        source_provider="helius",
        lookup_key="pair-2",
        lookup_type="pair_address",
    )

    assert batch["tx_batch_status"] in {"partial", "malformed"}
    assert batch["tx_batch_record_count"] == 1
    assert "signature_missing_synthesized" in batch["warnings"]
