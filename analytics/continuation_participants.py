"""Participant-role hygiene helpers for continuation metrics.

These helpers keep short-horizon continuation metrics focused on
interpretable organic flow rather than raw transfer noise. The goal is
not to perfectly classify every wallet; it is to exclude clearly
technical actors and treat ambiguous role attribution conservatively.
"""

from __future__ import annotations

from typing import Any

_TECHNICAL_HINTS = (
    "lp",
    "pool",
    "pair",
    "router",
    "vault",
    "amm",
    "market",
    "liquidity",
    "reserve",
    "program",
    "sysvar",
    "tokenkeg",
    "raydium",
    "jupiter",
)
_SYSTEM_HINTS = (
    "system",
    "program",
    "sysvar",
    "111111",
    "compute_budget",
)
_CREATOR_HINT_KEYS = (
    "creator_linked",
    "creator_overlap",
    "creator_related",
    "dev_linked",
    "deployer_linked",
    "treasury_linked",
)
_CREATOR_HINT_TERMS = ("creator", "deployer", "dev", "treasury")
_WALLET_KEYS = ("wallet", "wallet_address", "address", "owner", "signer", "fee_payer", "actor")


class ContinuationActorClass:
    ORGANIC = "organic"
    TECHNICAL_LIQUIDITY = "technical_liquidity"
    SYSTEM_OR_PROGRAM = "system_or_program"
    CREATOR_OR_DEV_RELATED = "creator_or_dev_related"
    AMBIGUOUS = "ambiguous"



def normalize_wallet(value: Any) -> str | None:
    if value is None:
        return None
    wallet = str(value).strip()
    return wallet or None



def participant_wallet(participant: dict[str, Any]) -> str | None:
    for key in _WALLET_KEYS:
        wallet = normalize_wallet(participant.get(key))
        if wallet:
            return wallet
    return None



def _looks_technical_liquidity(wallet: str) -> bool:
    lowered = wallet.lower()
    return any(hint in lowered for hint in _TECHNICAL_HINTS)



def _looks_system_or_program(wallet: str) -> bool:
    lowered = wallet.lower()
    return any(hint in lowered for hint in _SYSTEM_HINTS)



def _participant_is_creator_or_dev_related(participant: dict[str, Any], *, creator_wallet: str | None = None) -> bool:
    wallet = participant_wallet(participant)
    if wallet and creator_wallet and wallet == creator_wallet:
        return True
    for key in _CREATOR_HINT_KEYS:
        value = participant.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y", "on"}:
            return True
    label_values = [participant.get("label"), participant.get("role"), participant.get("wallet_label")]
    for value in label_values:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered and any(term in lowered for term in _CREATOR_HINT_TERMS):
                return True
    return False



def build_continuation_participant_context(
    txs: list[dict[str, Any]],
    *,
    creator_wallet: str | None = None,
) -> dict[str, Any]:
    participant_records: list[dict[str, Any]] = []
    organic_wallets: set[str] = set()
    creator_dev_wallets: set[str] = set()
    for tx in txs:
        participants = tx.get("participants")
        if not isinstance(participants, list):
            continue
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            participant_records.append(participant)
            wallet = participant_wallet(participant)
            if not wallet:
                continue
            if _participant_is_creator_or_dev_related(participant, creator_wallet=creator_wallet):
                creator_dev_wallets.add(wallet)
                continue
            organic_wallets.add(wallet)

    creator = normalize_wallet(creator_wallet)
    if creator:
        creator_dev_wallets.add(creator)
        organic_wallets.discard(creator)

    return {
        "participant_records": participant_records,
        "organic_wallets": organic_wallets,
        "creator_dev_wallets": creator_dev_wallets,
    }



def classify_continuation_participant(
    wallet: str | None,
    *,
    context: dict[str, Any] | None = None,
    tx_role_sides: dict[str, set[str]] | None = None,
) -> str:
    normalized = normalize_wallet(wallet)
    if not normalized:
        return ContinuationActorClass.AMBIGUOUS
    if tx_role_sides and len(tx_role_sides.get(normalized, set())) > 1:
        return ContinuationActorClass.AMBIGUOUS
    if _looks_system_or_program(normalized):
        return ContinuationActorClass.SYSTEM_OR_PROGRAM
    if _looks_technical_liquidity(normalized):
        return ContinuationActorClass.TECHNICAL_LIQUIDITY

    ctx = context if isinstance(context, dict) else {}
    creator_dev_wallets = ctx.get("creator_dev_wallets") if isinstance(ctx.get("creator_dev_wallets"), set) else set()
    organic_wallets = ctx.get("organic_wallets") if isinstance(ctx.get("organic_wallets"), set) else set()

    if normalized in creator_dev_wallets:
        return ContinuationActorClass.CREATOR_OR_DEV_RELATED
    if normalized in organic_wallets:
        return ContinuationActorClass.ORGANIC
    return ContinuationActorClass.AMBIGUOUS



def extract_tx_role_sides(tx: dict[str, Any]) -> dict[str, set[str]]:
    wallet_sides: dict[str, set[str]] = {}
    transfers = tx.get("tokenTransfers")
    if not isinstance(transfers, list):
        return wallet_sides
    for transfer in transfers:
        if not isinstance(transfer, dict):
            continue
        buyer = normalize_wallet(transfer.get("toUserAccount") or transfer.get("toUser") or transfer.get("buyer"))
        seller = normalize_wallet(transfer.get("fromUserAccount") or transfer.get("fromUser") or transfer.get("seller"))
        if buyer:
            wallet_sides.setdefault(buyer, set()).add("buy")
        if seller:
            wallet_sides.setdefault(seller, set()).add("sell")
    return wallet_sides



def normalize_continuation_transfer_role(
    transfer: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    tx_role_sides: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    buyer = normalize_wallet(transfer.get("toUserAccount") or transfer.get("toUser") or transfer.get("buyer"))
    seller = normalize_wallet(transfer.get("fromUserAccount") or transfer.get("fromUser") or transfer.get("seller"))
    buyer_class = classify_continuation_participant(buyer, context=context, tx_role_sides=tx_role_sides)
    seller_class = classify_continuation_participant(seller, context=context, tx_role_sides=tx_role_sides)
    return {
        "buyer": buyer if buyer_class == ContinuationActorClass.ORGANIC else None,
        "seller": seller if seller_class == ContinuationActorClass.ORGANIC else None,
        "buyer_class": buyer_class,
        "seller_class": seller_class,
    }


__all__ = [
    "ContinuationActorClass",
    "build_continuation_participant_context",
    "classify_continuation_participant",
    "extract_tx_role_sides",
    "normalize_continuation_transfer_role",
    "normalize_wallet",
    "participant_wallet",
]
