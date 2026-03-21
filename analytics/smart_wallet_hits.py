"""Early smart-wallet interaction signals."""

from __future__ import annotations

from datetime import datetime
from typing import Any


_ACTIVITY_TERMS = ("swap", "buy", "transfer", "receive")


def _parse_pair_ts(token_ctx: dict[str, Any]) -> int:
    raw = str(token_ctx.get("pair_created_at") or "")
    if not raw:
        return 0
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _is_historical_mode(token_ctx: dict[str, Any]) -> bool:
    if bool(token_ctx.get("historical_mode")):
        return True
    replay_origin = str(token_ctx.get("replay_input_origin") or "").lower()
    replay_status = str(token_ctx.get("replay_data_status") or "").lower()
    return replay_origin.startswith("historical") or replay_status.startswith("historical")


def _tx_matches_window(tx: dict[str, Any], *, pair_ts: int, window_sec: int, mint: str) -> bool:
    ts = int(tx.get("timestamp") or tx.get("blockTime") or 0)
    if pair_ts <= 0 or ts <= 0 or not (pair_ts <= ts <= pair_ts + window_sec):
        return False
    text = f"{tx.get('type', '')} {tx.get('description', '')} {tx.get('source', '')}".lower()
    mint_text = str(mint or "").lower()
    return any(word in text for word in _ACTIVITY_TERMS) and (mint_text in text or mint_text == "")


def _extract_records(result: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(result, dict):
        records = result.get("records") if isinstance(result.get("records"), list) else []
        return records, result
    if isinstance(result, list):
        return result, {}
    return [], {}


def compute_smart_wallet_hits(mint: str, seed_wallets: list[str], token_ctx: dict) -> dict[str, Any]:
    rpc_get_token_accounts_by_owner = token_ctx.get("rpc_get_token_accounts_by_owner")
    helius_get_transactions_by_address = token_ctx.get("helius_get_transactions_by_address")
    helius_get_transactions_by_address_with_status = token_ctx.get("helius_get_transactions_by_address_with_status")
    window_sec = int(token_ctx.get("smart_wallet_hit_window_sec") or 300)
    pair_ts = _parse_pair_ts(token_ctx)
    historical_mode = _is_historical_mode(token_ctx)

    hits: list[str] = []
    degraded = False
    warnings: list[str] = []
    tx_fetch_modes: list[str] = []

    for wallet in seed_wallets:
        has_account = False
        early_activity = False

        if not historical_mode and callable(rpc_get_token_accounts_by_owner):
            result = rpc_get_token_accounts_by_owner(wallet, mint)
            entries = result.get("value", []) if isinstance(result, dict) else []
            has_account = len(entries) > 0
        elif historical_mode and callable(rpc_get_token_accounts_by_owner):
            warnings.append("historical_mode_owner_balance_disabled")

        tx_records: list[dict[str, Any]] = []
        tx_meta: dict[str, Any] = {}
        limit = int(token_ctx.get("helius_tx_addr_limit", 40))
        if callable(helius_get_transactions_by_address_with_status):
            result = helius_get_transactions_by_address_with_status(
                wallet,
                limit,
                fetch_all=historical_mode,
                stop_ts=pair_ts if historical_mode and pair_ts > 0 else None,
            )
            tx_records, tx_meta = _extract_records(result)
        elif callable(helius_get_transactions_by_address):
            tx_records, tx_meta = _extract_records(helius_get_transactions_by_address(wallet, limit))

        tx_fetch_mode = str(tx_meta.get("tx_fetch_mode") or ("historical_scan" if historical_mode and tx_records else "direct"))
        if tx_fetch_mode:
            tx_fetch_modes.append(tx_fetch_mode)

        for tx in tx_records:
            if _tx_matches_window(tx, pair_ts=pair_ts, window_sec=window_sec, mint=mint):
                early_activity = True
                break

        if historical_mode and not tx_records:
            degraded = True
            warnings.append(f"historical_wallet_evidence_missing:{wallet}")

        if has_account or early_activity:
            hits.append(wallet)

    warnings = sorted(dict.fromkeys(warnings))
    return {
        "smart_wallet_hits": len(hits),
        "smart_wallet_hit_wallets": sorted(hits),
        "smart_wallet_hit_mode": "historical" if historical_mode else "current",
        "smart_wallet_hit_status": "degraded" if degraded else "ok",
        "smart_wallet_hit_warnings": warnings,
        "smart_wallet_tx_fetch_modes": sorted(dict.fromkeys(tx_fetch_modes)),
    }
