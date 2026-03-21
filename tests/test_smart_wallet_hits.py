import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.smart_wallet_hits import compute_smart_wallet_hits


def test_compute_smart_wallet_hits_counts_seed_hits():
    def rpc_get_token_accounts_by_owner(owner, mint):
        if owner == "wallet_hit":
            return {"value": [{"pubkey": "tokenacct"}]}
        return {"value": []}

    def helius_get_transactions_by_address(address, limit):
        return [{"timestamp": 1000, "type": "SWAP", "description": "buy token"}] if address == "wallet_hit" else []

    result = compute_smart_wallet_hits(
        "mint",
        ["wallet_hit", "wallet_miss"],
        {
            "pair_created_at": "1970-01-01T00:16:40Z",
            "rpc_get_token_accounts_by_owner": rpc_get_token_accounts_by_owner,
            "helius_get_transactions_by_address": helius_get_transactions_by_address,
            "smart_wallet_hit_window_sec": 300,
        },
    )

    assert result["smart_wallet_hits"] == 1
    assert result["smart_wallet_hit_wallets"] == ["wallet_hit"]


def test_historical_mode_uses_tx_window_and_skips_current_owner_balance_path():
    calls = {"rpc": 0, "helius": 0}

    def rpc_get_token_accounts_by_owner(owner, mint):
        calls["rpc"] += 1
        return {"value": [{"pubkey": f"{owner}:{mint}"}]}

    def helius_get_transactions_by_address_with_status(address, limit, *, fetch_all=False, stop_ts=None):
        calls["helius"] += 1
        assert fetch_all is True
        assert stop_ts == 1000
        return {
            "records": [
                {"timestamp": 1010, "type": "SWAP", "description": "buy mint"},
            ],
            "tx_fetch_mode": "historical_scan",
        }

    result = compute_smart_wallet_hits(
        "mint",
        ["wallet_hit"],
        {
            "pair_created_at": "1970-01-01T00:16:40Z",
            "historical_mode": True,
            "rpc_get_token_accounts_by_owner": rpc_get_token_accounts_by_owner,
            "helius_get_transactions_by_address_with_status": helius_get_transactions_by_address_with_status,
            "smart_wallet_hit_window_sec": 60,
        },
    )

    assert calls["rpc"] == 0
    assert calls["helius"] == 1
    assert result["smart_wallet_hits"] == 1
    assert result["smart_wallet_hit_mode"] == "historical"
    assert result["smart_wallet_hit_status"] == "ok"
    assert result["smart_wallet_tx_fetch_modes"] == ["historical_scan"]


def test_historical_mode_degrades_honestly_when_wallet_evidence_is_missing():
    result = compute_smart_wallet_hits(
        "mint",
        ["wallet_a"],
        {
            "pair_created_at": "1970-01-01T00:16:40Z",
            "historical_mode": True,
            "helius_get_transactions_by_address_with_status": lambda *args, **kwargs: {"records": [], "tx_fetch_mode": "historical_scan"},
        },
    )

    assert result["smart_wallet_hits"] == 0
    assert result["smart_wallet_hit_status"] == "degraded"
    assert any(item.startswith("historical_wallet_evidence_missing:") for item in result["smart_wallet_hit_warnings"])
