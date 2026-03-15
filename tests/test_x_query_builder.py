import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.x_query_builder import build_queries


def test_build_queries_capped_and_deduped(monkeypatch):
    monkeypatch.setenv("OPENCLAW_X_QUERY_MAX", "4")
    token = {
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "exaMple",
        "name": "Example Coin",
    }
    queries = build_queries(token)
    assert len(queries) <= 4
    assert len({item["normalized_query"] for item in queries}) == len(queries)


def test_build_queries_handles_missing_name_or_symbol(monkeypatch):
    monkeypatch.setenv("OPENCLAW_X_QUERY_MAX", "4")
    token = {"token_address": "So11111111111111111111111111111111111111112", "name": "Only Name"}
    queries = build_queries(token)
    assert len(queries) >= 1
    assert all(item["query"] for item in queries)


def test_contract_query_only_for_valid_mint(monkeypatch):
    monkeypatch.setenv("OPENCLAW_X_QUERY_MAX", "4")
    valid = build_queries({"token_address": "So11111111111111111111111111111111111111112"})
    invalid = build_queries({"token_address": "0xdeadbeef"})
    assert any(item["query_type"] == "contract" for item in valid)
    assert not any(item["query_type"] == "contract" for item in invalid)
