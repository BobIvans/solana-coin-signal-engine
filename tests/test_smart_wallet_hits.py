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



def test_compute_smart_wallet_hits_prefers_batch_holder_lookup():
    call_log: list[tuple[str, str]] = []

    def rpc_get_mint_holder_owners(mint):
        call_log.append(("batch", mint))
        return ["wallet_hit"]

    def rpc_get_token_accounts_by_owner(owner, mint):
        call_log.append(("per_wallet", owner))
        return {"value": []}

    result = compute_smart_wallet_hits(
        "mint",
        ["wallet_hit", "wallet_miss"],
        {
            "pair_created_at": "1970-01-01T00:16:40Z",
            "rpc_get_mint_holder_owners": rpc_get_mint_holder_owners,
            "rpc_get_token_accounts_by_owner": rpc_get_token_accounts_by_owner,
            "helius_get_transactions_by_address": lambda address, limit: [],
            "smart_wallet_hit_window_sec": 300,
        },
    )

    assert result["smart_wallet_hits"] == 1
    assert result["smart_wallet_hit_wallets"] == ["wallet_hit"]
    assert call_log == [("batch", "mint")]
