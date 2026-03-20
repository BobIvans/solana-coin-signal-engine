from __future__ import annotations

from pathlib import Path

from collectors.helius_client import HeliusClient
from collectors.solana_rpc_client import SolanaRpcClient
from data.tx_lake import load_tx_batch
from data.tx_normalizer import normalize_tx_batch
from data.tx_lake import write_tx_batch


class FakeHeliusClient(HeliusClient):
    def __init__(self, *args, raw_result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_result = raw_result

    def _get(self, endpoint, params):
        return self.raw_result


class FakeSolanaRpcClient(SolanaRpcClient):
    def __init__(self, *args, raw_result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_result = raw_result

    def _rpc(self, method, params):
        if method == "getSignaturesForAddress":
            return self.raw_result
        return None


STALE_BATCH = normalize_tx_batch(
    [{"signature": "stale-sig", "timestamp": 1_710_000_000, "slot": 99, "nativeTransfers": []}],
    source_provider="helius",
    lookup_key="pair-stale",
    lookup_type="address",
    fetched_at="2026-03-19T08:00:00Z",
    normalized_at="2026-03-19T08:00:00Z",
    tx_batch_origin="fixture",
    tx_batch_freshness="stale_cache_allowed",
)


def test_helius_client_uses_stale_fallback_when_upstream_fails(tmp_path: Path):
    write_tx_batch(STALE_BATCH, root_dir=tmp_path, provider="helius", lookup_key="pair-stale", lookup_type="address")
    client = FakeHeliusClient("demo", tx_lake_dir=str(tmp_path), tx_cache_ttl_sec=60, stale_tx_cache_ttl_sec=200000, raw_result=None)

    result = client.get_transactions_by_address_with_status("pair-stale", limit=10)

    assert result["tx_fetch_mode"] == "upstream_failed_use_stale"
    assert result["tx_batch_record_count"] == 1
    assert result["records"][0]["signature"] == "stale-sig"


def test_solana_rpc_client_writes_fresh_batch_and_reuses_it(tmp_path: Path):
    client = FakeSolanaRpcClient(
        "https://rpc.invalid",
        tx_lake_dir=str(tmp_path),
        tx_cache_ttl_sec=1000,
        raw_result=[{"signature": "sig-1", "slot": 101, "blockTime": 1710000000, "err": None}],
    )
    first = client.get_signatures_for_address_with_status("wallet-1", limit=5)
    assert first["tx_batch_record_count"] == 1
    stored = load_tx_batch(lookup_key="wallet-1", lookup_type="address", provider="solana_rpc", root_dir=tmp_path)
    assert stored is not None
    client.raw_result = None
    second = client.get_signatures_for_address_with_status("wallet-1", limit=5)
    assert second["tx_fetch_mode"] == "fresh_cache"
    assert second["records"][0]["signature"] == "sig-1"
