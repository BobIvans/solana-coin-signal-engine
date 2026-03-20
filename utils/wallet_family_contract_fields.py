"""Shared wallet-family token-facing contract field helpers."""

from __future__ import annotations

from typing import Any

SMART_WALLET_FAMILY_ARRAY_FIELDS = [
    "smart_wallet_family_ids",
    "smart_wallet_independent_family_ids",
    "smart_wallet_family_origins",
    "smart_wallet_family_statuses",
    "smart_wallet_family_reason_codes",
]

SMART_WALLET_FAMILY_NUMERIC_FIELDS = [
    "smart_wallet_family_unique_count",
    "smart_wallet_independent_family_unique_count",
    "smart_wallet_family_confidence_max",
    "smart_wallet_family_member_count_max",
]

SMART_WALLET_FAMILY_FLAG_FIELDS = [
    "smart_wallet_family_shared_funder_flag",
    "smart_wallet_family_creator_link_flag",
]

SMART_WALLET_FAMILY_CONTRACT_FIELDS = [
    *SMART_WALLET_FAMILY_ARRAY_FIELDS,
    *SMART_WALLET_FAMILY_NUMERIC_FIELDS,
    *SMART_WALLET_FAMILY_FLAG_FIELDS,
]


def default_wallet_family_contract_fields() -> dict[str, Any]:
    return {
        "smart_wallet_family_ids": [],
        "smart_wallet_independent_family_ids": [],
        "smart_wallet_family_origins": [],
        "smart_wallet_family_statuses": [],
        "smart_wallet_family_reason_codes": [],
        "smart_wallet_family_unique_count": 0,
        "smart_wallet_independent_family_unique_count": 0,
        "smart_wallet_family_confidence_max": 0.0,
        "smart_wallet_family_member_count_max": 0,
        "smart_wallet_family_shared_funder_flag": False,
        "smart_wallet_family_creator_link_flag": False,
    }


def copy_wallet_family_contract_fields(
    source: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy wallet-family token-facing fields with defaulted fallbacks."""

    fallback = fallback or {}
    defaults = default_wallet_family_contract_fields()
    output: dict[str, Any] = {}
    for field in SMART_WALLET_FAMILY_CONTRACT_FIELDS:
        if field in source:
            output[field] = source.get(field)
        elif field in fallback:
            output[field] = fallback.get(field)
        else:
            output[field] = defaults[field]
    return output
