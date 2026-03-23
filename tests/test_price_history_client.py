from __future__ import annotations

from collectors.price_history_client import PriceHistoryClient, validate_price_history_provider_config



def test_price_history_client_normalizes_geckoterminal_provider_aliases():
    assert PriceHistoryClient(provider="geckoterminal").provider == "geckoterminal_pool_ohlcv"
    assert PriceHistoryClient(provider="geckoterminal_pool").provider == "geckoterminal_pool_ohlcv"
    assert PriceHistoryClient(provider="geckoterminal_pool_ohlcv").provider == "geckoterminal_pool_ohlcv"



def test_validate_price_history_provider_config_accepts_geckoterminal_defaults():
    config = validate_price_history_provider_config({"provider": "geckoterminal"})

    assert config["provider"] == "geckoterminal_pool_ohlcv"
    assert config["provider_bootstrap_ok"] is True
    assert config["allow_pairless_token_lookup"] is True
    assert config["require_pair_address"] is False
    assert config["request_version"] == "20230302"
    assert config["currency"] == "usd"
    assert config["include_empty_intervals"] is True



def test_fetch_price_path_resolves_pool_before_fetching_geckoterminal_ohlcv(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv")
    calls = []

    def fake_get(endpoint, params, *, headers=None):
        calls.append((endpoint, dict(params)))
        if endpoint.endswith("/tokens/token-1/pools"):
            return {
                "json": {
                    "data": [
                        {
                            "attributes": {
                                "address": "pool-1",
                                "reserve_in_usd": "100",
                                "volume_usd": {"h24": "50"},
                            }
                        }
                    ]
                },
                "http_status": 200,
            }
        return {
            "json": {"data": {"attributes": {"ohlcv_list": [[1000, 1, 2, 0.5, 1.5, 11]]}}},
            "http_status": 200,
        }

    monkeypatch.setattr(client, "_get", fake_get)
    result = client.fetch_price_path(token_address="token-1", start_ts=1000, end_ts=1000, interval_sec=60)

    assert calls[0][0].endswith("/tokens/token-1/pools")
    assert calls[1][0].endswith("/pools/pool-1/ohlcv/minute")
    assert result["selected_pool_address"] == "pool-1"
    assert result["price_path_status"] == "complete"



def test_fetch_price_path_normalizes_geckoterminal_ohlcv_list(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv")

    def fake_get(endpoint, params, *, headers=None):
        if endpoint.endswith("/tokens/token-2/pools"):
            return {
                "json": {"data": [{"attributes": {"address": "pool-2", "reserve_in_usd": "100", "volume_usd": {"h24": "40"}}}]},
                "http_status": 200,
            }
        return {
            "json": {"data": {"attributes": {"ohlcv_list": [[1060, 1.0, 1.3, 0.9, 1.2, 12], [1000, 0.8, 1.1, 0.7, 1.0, 9]]}}},
            "http_status": 200,
        }

    monkeypatch.setattr(client, "_get", fake_get)
    result = client.fetch_price_path(token_address="token-2", start_ts=1000, end_ts=1060, interval_sec=60)

    assert result["price_path"] == [
        {"timestamp": 1000, "offset_sec": 0, "price": 1.0, "volume": 9.0, "open": 0.8, "high": 1.1, "low": 0.7, "close": 1.0},
        {"timestamp": 1060, "offset_sec": 60, "price": 1.2, "volume": 12.0, "open": 1.0, "high": 1.3, "low": 0.9, "close": 1.2},
    ]



def test_fetch_price_path_marks_missing_when_pool_resolution_returns_no_candidates(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv")

    monkeypatch.setattr(client, "_get", lambda endpoint, params, *, headers=None: {"json": {"data": []}, "http_status": 200})
    result = client.fetch_price_path(token_address="token-3", start_ts=1000, end_ts=1060, interval_sec=60)

    assert result["missing"] is True
    assert result["warning"] == "pool_resolution_failed"
    assert result["pool_resolution_status"] == "pool_resolution_failed"



def test_fetch_price_path_keeps_pool_resolution_provenance_fields(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv")

    def fake_get(endpoint, params, *, headers=None):
        if endpoint.endswith("/tokens/token-4/pools"):
            return {
                "json": {
                    "data": [
                        {"attributes": {"address": "pool-4a", "reserve_in_usd": "100", "volume_usd": {"h24": "50"}}},
                        {"attributes": {"address": "pool-4b", "reserve_in_usd": "90", "volume_usd": {"h24": "60"}}},
                    ]
                },
                "http_status": 200,
            }
        return {"json": {"data": {"attributes": {"ohlcv_list": [[1000, 1, 1, 1, 1, 1]]}}}, "http_status": 200}

    monkeypatch.setattr(client, "_get", fake_get)
    result = client.fetch_price_path(token_address="token-4", start_ts=1000, end_ts=1000, interval_sec=60)

    assert result["pool_resolver_source"] == "geckoterminal"
    assert result["pool_resolver_confidence"] == "high"
    assert result["pool_candidates_seen"] == 2
    assert result["selected_pool_address"] == "pool-4a"



def test_fetch_price_path_uses_include_empty_intervals_for_minute_series(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv")
    seen_params = []

    def fake_get(endpoint, params, *, headers=None):
        if endpoint.endswith("/tokens/token-5/pools"):
            return {"json": {"data": [{"attributes": {"address": "pool-5", "reserve_in_usd": "100", "volume_usd": {"h24": "10"}}}]}, "http_status": 200}
        seen_params.append(dict(params))
        return {"json": {"data": {"attributes": {"ohlcv_list": [[1000, 1, 1, 1, 1, 0]]}}}, "http_status": 200}

    monkeypatch.setattr(client, "_get", fake_get)
    client.fetch_price_path(token_address="token-5", start_ts=1000, end_ts=1000, interval_sec=60)

    assert seen_params[0]["include_empty_intervals"] == "true"
    assert seen_params[0]["aggregate"] == 1



def test_fetch_price_path_paginates_backwards_with_before_timestamp_when_range_exceeds_limit(monkeypatch):
    client = PriceHistoryClient(provider="geckoterminal_pool_ohlcv", provider_config={"max_ohlcv_limit": 2})
    before_timestamps = []

    def fake_get(endpoint, params, *, headers=None):
        if endpoint.endswith("/tokens/token-6/pools"):
            return {"json": {"data": [{"attributes": {"address": "pool-6", "reserve_in_usd": "100", "volume_usd": {"h24": "10"}}}]}, "http_status": 200}
        before_timestamps.append(params.get("before_timestamp"))
        if len(before_timestamps) == 1:
            rows = [[1180, 1, 1, 1, 1.2, 4], [1120, 1, 1, 1, 1.1, 3]]
        else:
            rows = [[1060, 1, 1, 1, 1.0, 2], [1000, 1, 1, 1, 0.9, 1]]
        return {"json": {"data": {"attributes": {"ohlcv_list": rows}}}, "http_status": 200}

    monkeypatch.setattr(client, "_get", fake_get)
    result = client.fetch_price_path(token_address="token-6", start_ts=1000, end_ts=1180, interval_sec=60)

    assert before_timestamps == [1180, 1060]
    assert [row["timestamp"] for row in result["price_path"]] == [1000, 1060, 1120, 1180]
