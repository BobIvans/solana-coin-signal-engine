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
            "selected_pool_address": "pool-selected",
            "pool_resolver_source": "geckoterminal",
            "pool_resolver_confidence": "high",
            "pool_candidates_seen": 3,
            "pool_resolution_status": "resolved",
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
            "selected_pool_address": kwargs.get("pair_address") or "pool-partial",
            "pool_resolver_source": "seed_pair_address" if kwargs.get("pair_address") else "geckoterminal",
            "pool_resolver_confidence": "hint" if kwargs.get("pair_address") else "high",
            "pool_candidates_seen": 1,
            "pool_resolution_status": "seed_pair_address" if kwargs.get("pair_address") else "resolved",
            "source_provider": "fake",
            "price_path": [{"timestamp": 1000, "offset_sec": 0, "price": 1.0}],
            "truncated": True,
            "missing": False,
            "price_path_status": "partial",
            "warning": "price_path_incomplete",
        }


class FakeMissingRowsPriceHistoryClient:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_price_path(self, **kwargs):
        return {
            "token_address": kwargs["token_address"],
            "pair_address": kwargs.get("pair_address"),
            "selected_pool_address": "pool-empty",
            "pool_resolver_source": "geckoterminal",
            "pool_resolver_confidence": "high",
            "pool_candidates_seen": 4,
            "pool_resolution_status": "resolved",
            "source_provider": "fake",
            "price_path": [],
            "truncated": False,
            "missing": True,
            "price_path_status": "missing",
            "warning": "no_pool_ohlcv_rows",
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


def test_collect_price_paths_embeds_selected_pool_address_from_provider_result(monkeypatch):
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePriceHistoryClient)
    rows = chain_backfill._collect_price_paths(
        {"token_address": "tok_pool", "pair_address": "pair_seed", "pair_created_at_ts": 1000},
        {},
        {"backfill": {"price_path_window_sec": 120, "price_interval_sec": 60}},
    )

    assert rows[0]["selected_pool_address"] == "pool-selected"
    assert rows[0]["pool_resolver_source"] == "geckoterminal"


def test_collect_price_paths_preserves_pool_resolution_diagnostics_on_missing_rows(monkeypatch):
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakeMissingRowsPriceHistoryClient)
    rows = chain_backfill._collect_price_paths(
        {"token_address": "tok_missing", "pair_address": "", "pair_created_at_ts": 1000},
        {},
        {"backfill": {"price_path_window_sec": 120, "price_interval_sec": 60}, "providers": {"price_history": {"provider": "geckoterminal_pool_ohlcv"}}},
    )

    assert rows[0]["warning"] == "no_pool_ohlcv_rows"
    assert rows[0]["selected_pool_address"] == "pool-empty"
    assert rows[0]["pool_resolution_status"] == "resolved"


def test_collect_price_paths_prefers_seed_pair_address_but_allows_provider_selected_pool_override(monkeypatch):
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePriceHistoryClient)
    rows = chain_backfill._collect_price_paths(
        {"token_address": "tok_seed", "pair_address": "pair_seed", "pair_created_at_ts": 1000},
        {},
        {"backfill": {"price_path_window_sec": 120, "price_interval_sec": 60}, "providers": {"price_history": {"provider": "geckoterminal_pool_ohlcv"}}},
    )

    assert rows[0]["pair_address"] == "pair_seed"
    assert rows[0]["selected_pool_address"] == "pool-selected"


def test_collect_price_paths_works_with_geckoterminal_pool_provider_and_replay_usable_minute_rows(monkeypatch):
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePriceHistoryClient)
    rows = chain_backfill._collect_price_paths(
        {"token_address": "tok_gecko", "pair_address": "", "pair_created_at_ts": 1000},
        {},
        {
            "backfill": {"price_path_window_sec": 120, "price_interval_sec": 60},
            "providers": {"price_history": {"provider": "geckoterminal_pool_ohlcv", "include_empty_intervals": True}},
        },
    )

    assert rows[0]["source_provider"] == "fake"
    assert len(rows[0]["price_path"]) == 2
    assert rows[0]["price_path"][1]["offset_sec"] == 60


def test_collect_price_paths_preserves_best_partial_result_for_geckoterminal_provider(monkeypatch):
    monkeypatch.setattr(chain_backfill, "PriceHistoryClient", FakePartialPriceHistoryClient)
    rows = chain_backfill._collect_price_paths(
        {"token_address": "tok_best_partial", "pair_address": "pair_partial", "pair_created_at_ts": 1000},
        {},
        {"backfill": {"price_path_window_sec": 120, "price_interval_sec": 60}, "providers": {"price_history": {"provider": "geckoterminal_pool_ohlcv"}}},
    )

    assert rows[0]["price_path_status"] == "partial"
    assert rows[0]["selected_pool_address"] == "pair_partial"
    assert rows[0]["pool_resolution_status"] == "seed_pair_address"
