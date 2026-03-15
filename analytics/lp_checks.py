"""LP burn/lock checks with strict burn-vs-lock separation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import read_json


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_lock_programs(settings: Any) -> set[str]:
    path = Path(getattr(settings, "RUG_LP_LOCK_PROGRAM_ALLOWLIST_PATH", ""))
    payload = read_json(path, default=[])
    if isinstance(payload, list):
        return {str(item) for item in payload if str(item).strip()}
    if isinstance(payload, dict):
        items = payload.get("program_ids", [])
        return {str(item) for item in items if str(item).strip()}
    return set()


def check_lp_state(token_ctx: dict, settings: Any) -> dict[str, Any]:
    flags: list[str] = []
    warnings: list[str] = []

    lp_balance = _as_float(token_ctx.get("lp_token_balance"))
    lp_owner = str(token_ctx.get("lp_owner") or "")
    lp_program = str(token_ctx.get("lp_program_id") or "")
    lp_recoverable = bool(token_ctx.get("lp_recoverable_by_creator", False))

    burn_allow = {
        str(item).strip()
        for item in str(getattr(settings, "RUG_LP_BURN_OWNER_ALLOWLIST", "")).split(",")
        if str(item).strip()
    }
    lock_allow = _load_lock_programs(settings)

    burn_owner_match = lp_owner in burn_allow
    lock_program_match = lp_program in lock_allow

    lp_burn_confirmed = bool(lp_balance <= 0 and burn_owner_match and not lock_program_match and not lp_recoverable)
    lp_locked_flag = bool(lock_program_match)

    burn_score = 0.9 if lp_burn_confirmed else (0.2 if burn_owner_match else 0.0)
    lock_score = 0.8 if lp_locked_flag else 0.0

    if lp_locked_flag and not lp_burn_confirmed:
        flags.append("lock_without_burn")
        warnings.append("lock detected but burn not confirmed")
    if lp_recoverable:
        flags.append("lp_recoverable_by_creator")
    if lp_balance <= 0 and not burn_owner_match and not lock_program_match:
        warnings.append("lp_state_ambiguous")

    return {
        "lp_burn_confirmed": lp_burn_confirmed,
        "lp_burn_evidence_score": round(burn_score, 4),
        "lp_locked_flag": lp_locked_flag,
        "lp_lock_evidence_score": round(lock_score, 4),
        "lp_lock_provider_label": "locker_program_match" if lp_locked_flag else "",
        "lp_flags": flags,
        "lp_warnings": warnings,
        "lp_explicit_recoverable": lp_recoverable,
    }
