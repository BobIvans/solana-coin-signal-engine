from __future__ import annotations

from src.replay import chain_backfill


class FakeRpcClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_signatures_for_address(self, address, limit=40):
        return [{"signature": "sig-1"}]

    def _rpc(self, method, params):
        if method == "getTransaction":
            return {"slot": 101}
        if method == "getBlockTime":
            return 1000
        return None


class FakePriceHistoryClient:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_price_path(self, **kwargs):
        return {
            "token_address": kwargs["token_address"],
            "pair_address": kwargs.get("pair_address"),
            "source_provider": "fake",
            "price_path": [
                {"timestamp": 1000, "offset_sec": 0, "price": 1.0},
                {"timestamp": 1060, "offset_sec": 60, "price": 1.1},
            ],
            "truncated": False,
            "missing": False,
            "price_path_status": "complete",
            "warning": None,
        }


class FakePartialPriceHistoryClient:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_price_path(self, **kwargs):
        return {
            "token_address": kwargs["token_address"],
            "pair_address": kwargs.get("pair_address"),
            "source_provider": "fake",
            "price_path": [{"timestamp": 1000, "offset_sec": 0, "price": 1.0}],
            "truncated": True,
            "missing": False,
            "price_path_status": "partial",
            "warning": "price_path_incomplete",
        }



def test_build_chain_context_embeds_replay_usable_price_paths(monkeypatch):
    monkeypatch.setattr(chain_backfill, "SolanaRpcClient", FakeRpcClient)
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePriceHistoryClient)
    rows = chain_backfill.build_chain_context(
        [{"token_address": "tok", "pair_address": "pair", "pair_created_at_ts": 1000}],
        {"backfill": {"cache_enabled": False, "max_signatures_per_address": 5, "price_path_window_sec": 120, "price_interval_sec": 60}},
        dry_run=False,
    )

    assert len(rows) == 1
    price_path = rows[0]["price_paths"][0]
    assert price_path["price_path"][1]["offset_sec"] == 60
    assert price_path["truncated"] is False



def test_build_chain_context_preserves_partial_price_history_status(monkeypatch):
    monkeypatch.setattr(chain_backfill, "SolanaRpcClient", FakeRpcClient)
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePartialPriceHistoryClient)
    rows = chain_backfill.build_chain_context(
        [{"token_address": "tok_partial", "pair_address": "pair_partial", "pair_created_at_ts": 1000}],
        {"backfill": {"cache_enabled": False, "max_signatures_per_address": 5, "price_path_window_sec": 120, "price_interval_sec": 60}},
        dry_run=False,
    )

    price_path = rows[0]["price_paths"][0]
    assert price_path["truncated"] is True
    assert price_path["price_path_status"] == "partial"
