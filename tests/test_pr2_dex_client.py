import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.dexscreener_client import fetch_discovery_pairs, normalize_pair


def test_normalize_pair_has_required_fields():
    raw = {
        "chainId": "solana",
        "dexId": "raydium",
        "pairAddress": "PAIR1",
        "pairCreatedAt": 1742049360000,
        "priceUsd": "0.001",
        "liquidity": {"usd": "22000"},
        "fdv": "500000",
        "marketCap": None,
        "volume": {"m5": "25000", "h1": "25000"},
        "txns": {"m5": {"buys": "30", "sells": "12"}},
        "baseToken": {"address": "TOKEN1", "symbol": "ABC", "name": "ABC Coin"},
        "boosts": {"active": True},
        "info": {"paid": False},
    }

    normalized = normalize_pair(raw)

    required = {
        "token_address",
        "pair_address",
        "symbol",
        "name",
        "chain",
        "dex_id",
        "pair_created_at",
        "pair_created_at_ts",
        "price_usd",
        "liquidity_usd",
        "fdv",
        "market_cap",
        "volume_m5",
        "volume_h1",
        "txns_m5_buys",
        "txns_m5_sells",
        "boost_flag",
        "paid_order_flag",
        "source",
    }
    assert required <= set(normalized.keys())
    assert isinstance(normalized["price_usd"], float)
    assert isinstance(normalized["txns_m5_buys"], int)


def test_normalize_pair_handles_missing_fields_safely():
    normalized = normalize_pair({})

    assert normalized["token_address"] == ""
    assert normalized["pair_address"] == ""
    assert normalized["price_usd"] == 0.0
    assert normalized["liquidity_usd"] == 0.0
    assert normalized["txns_m5_buys"] == 0
    assert normalized["pair_created_at"] is None
    assert normalized["pair_created_at_ts"] == 0


class _DiscoverySettings:
    DISCOVERY_PROVIDER_MODE = "search"
    DISCOVERY_ALLOW_DEX_SEARCH_FALLBACK = True


def test_discovery_fetch_uses_provider_mode_and_marks_source_metadata(monkeypatch):
    raw_pair = {
        "chainId": "solana",
        "pairAddress": "PAIR_META",
        "pairCreatedAt": 1_000,
        "baseToken": {"address": "TOKEN_META", "symbol": "META", "name": "Meta"},
    }
    monkeypatch.setattr("collectors.dexscreener_client.fetch_latest_solana_pairs", lambda: [raw_pair])

    pairs = fetch_discovery_pairs(_DiscoverySettings())
    normalized = normalize_pair(pairs[0], discovery_seen_ts=1_020)

    assert normalized["discovery_source"] == "dexscreener_search"
    assert normalized["discovery_source_mode"] == "fallback_search"
    assert 0 <= normalized["discovery_source_confidence"] < 0.5


def test_search_feed_is_marked_as_fallback_source_mode():
    normalized = normalize_pair(
        {
            "chainId": "solana",
            "pairAddress": "PAIR_FB",
            "pairCreatedAt": 1_000,
            "baseToken": {"address": "TOKEN_FB", "symbol": "FB", "name": "Fallback"},
        },
        discovery_seen_ts=1_010,
    )
    assert normalized["discovery_source_mode"] == "fallback_search"
    assert normalized["discovery_source_confidence"] < 0.5
