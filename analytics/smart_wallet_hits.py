"""Early smart-wallet interaction signals."""

from __future__ import annotations

from datetime import datetime
from typing import Any



def _parse_pair_ts(token_ctx: dict[str, Any]) -> int:
    raw = str(token_ctx.get("pair_created_at") or "")
    if not raw:
        return 0
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0



def _mint_holders_from_batch(mint: str, token_ctx: dict[str, Any]) -> set[str]:
    batch_fetch = token_ctx.get("rpc_get_mint_holder_owners")
    if callable(batch_fetch):
        return {str(wallet) for wallet in (batch_fetch(mint) or []) if str(wallet).strip()}
    rpc_client = token_ctx.get("rpc_client")
    if rpc_client is not None and hasattr(rpc_client, "get_mint_holder_owners"):
        return {str(wallet) for wallet in (rpc_client.get_mint_holder_owners(mint) or []) if str(wallet).strip()}
    return set()



def compute_smart_wallet_hits(mint: str, seed_wallets: list[str], token_ctx: dict) -> dict[str, Any]:
    rpc_get_token_accounts_by_owner = token_ctx.get("rpc_get_token_accounts_by_owner")
    helius_get_transactions_by_address = token_ctx.get("helius_get_transactions_by_address")
    window_sec = int(token_ctx.get("smart_wallet_hit_window_sec") or 300)
    pair_ts = _parse_pair_ts(token_ctx)

    seed_wallet_set = {str(wallet) for wallet in seed_wallets if str(wallet).strip()}
    holders = _mint_holders_from_batch(mint, token_ctx)
    hits = sorted(seed_wallet_set & holders)
    remaining_wallets = sorted(seed_wallet_set - set(hits))

    if not holders:
        for wallet in seed_wallets:
            has_account = False
            if callable(rpc_get_token_accounts_by_owner):
                result = rpc_get_token_accounts_by_owner(wallet, mint)
                entries = result.get("value", []) if isinstance(result, dict) else []
                has_account = len(entries) > 0
            if has_account and wallet not in hits:
                hits.append(wallet)
        remaining_wallets = sorted(seed_wallet_set - set(hits))

    for wallet in remaining_wallets:
        early_activity = False
        if callable(helius_get_transactions_by_address):
            txs = helius_get_transactions_by_address(wallet, token_ctx.get("helius_tx_addr_limit", 40))
            for tx in txs:
                ts = int(tx.get("timestamp") or tx.get("blockTime") or 0)
                if pair_ts > 0 and ts > 0 and pair_ts <= ts <= pair_ts + window_sec:
                    text = f"{tx.get('type','')} {tx.get('description','')}".lower()
                    if any(word in text for word in ("swap", "buy", "transfer", "receive")):
                        early_activity = True
                        break

        if early_activity and wallet not in hits:
            hits.append(wallet)

    return {
        "smart_wallet_hits": len(hits),
        "smart_wallet_hit_wallets": sorted(hits),
    }
