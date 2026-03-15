"""Authority safety checks for rug-risk assessment."""

from __future__ import annotations

from typing import Any


def _is_revoked(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"", "none", "null", "revoked"}
    return False


def check_authorities(token_ctx: dict) -> dict[str, Any]:
    mint_revoked = _is_revoked(token_ctx.get("mint_authority"))
    freeze_revoked = _is_revoked(token_ctx.get("freeze_authority"))

    flags: list[str] = []
    if not mint_revoked:
        flags.append("mint_active")
    if not freeze_revoked:
        flags.append("freeze_active")

    return {
        "mint_revoked": mint_revoked,
        "freeze_revoked": freeze_revoked,
        "authority_flags": flags,
    }
