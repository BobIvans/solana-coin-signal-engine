"""Dev wallet estimation and early sell-pressure computation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_ts(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def infer_dev_wallet(token_ctx: dict, txs: list[dict]) -> dict[str, Any]:
    candidates = []
    for key in ("creator_wallet", "deployer_wallet", "mint_authority", "update_authority"):
        value = str(token_ctx.get(key) or "")
        if value:
            candidates.append(value)
    if candidates:
        return {"dev_wallet_est": candidates[0], "dev_wallet_confidence_score": 0.74}

    signers: dict[str, int] = {}
    for tx in txs[:25]:
        signer = str(tx.get("feePayer") or tx.get("signer") or "")
        if signer:
            signers[signer] = signers.get(signer, 0) + 1
    if not signers:
        return {"dev_wallet_est": "", "dev_wallet_confidence_score": 0.1}

    winner = sorted(signers.items(), key=lambda item: (-item[1], item[0]))[0][0]
    max_hits = max(signers.values())
    confidence = min(0.7, 0.3 + max_hits / max(len(txs), 1))
    return {"dev_wallet_est": winner, "dev_wallet_confidence_score": round(confidence, 4)}


def compute_dev_sell_pressure_5m(dev_wallet: str, token_ctx: dict, txs: list[dict]) -> dict[str, Any]:
    pair_created_ts = _parse_ts(str(token_ctx.get("pair_created_at") or ""))
    if pair_created_ts <= 0:
        return {"dev_sell_pressure_5m": None, "unique_buyers_5m": 0, "holder_growth_5m": 0}

    sold = 0.0
    bought_or_received = 0.0
    buyers: set[str] = set()

    for tx in txs:
        ts = int(tx.get("timestamp") or tx.get("blockTime") or 0)
        if ts <= 0 or ts < pair_created_ts or ts > pair_created_ts + 300:
            continue

        account_data = tx.get("accountData", []) if isinstance(tx.get("accountData"), list) else []
        for item in account_data:
            acct = str(item.get("account") or "")
            change = float(item.get("tokenBalanceChanges", 0) or 0)
            if change > 0 and acct:
                buyers.add(acct)

        events = tx.get("tokenTransfers", []) if isinstance(tx.get("tokenTransfers"), list) else []
        for event in events:
            from_user = str(event.get("fromUserAccount") or "")
            to_user = str(event.get("toUserAccount") or "")
            amount = float(event.get("tokenAmount") or 0)
            if from_user == dev_wallet:
                sold += max(0.0, amount)
            if to_user == dev_wallet:
                bought_or_received += max(0.0, amount)

    pressure = sold / max(bought_or_received, 1e-9)
    return {
        "dev_sell_pressure_5m": round(pressure, 6),
        "unique_buyers_5m": len(buyers),
        "holder_growth_5m": len(buyers),
    }
