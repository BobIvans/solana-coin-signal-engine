"""Rug safety assessment engine for enriched Solana tokens."""

from __future__ import annotations

from typing import Any

from analytics.authority_checks import check_authorities
from analytics.concentration_checks import check_concentration
from analytics.dev_risk_checks import check_dev_risk
from analytics.lp_checks import check_lp_state
from utils.clock import utc_now_iso

CONTRACT_VERSION = "rug_safety_v1"


def _authority_risk(mint_revoked: bool, freeze_revoked: bool) -> float:
    if mint_revoked and freeze_revoked:
        return 0.0
    if mint_revoked ^ freeze_revoked:
        return 0.35
    if not mint_revoked and not freeze_revoked:
        return 0.9
    return 0.7


def _lp_risk(lp: dict[str, Any]) -> float:
    if lp.get("lp_burn_confirmed"):
        return 0.0
    if lp.get("lp_explicit_recoverable"):
        return 0.9
    if lp.get("lp_locked_flag"):
        return 0.18
    if lp.get("lp_warnings"):
        return 0.45
    return 0.45


def _launch_path_risk(token_ctx: dict[str, Any]) -> float:
    label = str(token_ctx.get("launch_path_label") or "")
    return 0.25 if not label or label == "unknown" else 0.05


def assess_rug_risk(token_ctx: dict, settings: Any) -> dict[str, Any]:
    authority = check_authorities(token_ctx)
    lp = check_lp_state(token_ctx, settings)
    concentration = check_concentration(token_ctx, settings)
    dev = check_dev_risk(token_ctx, settings)

    authority_risk = _authority_risk(authority["mint_revoked"], authority["freeze_revoked"])
    lp_risk = _lp_risk(lp)
    concentration_risk = float(concentration["concentration_penalty"])
    dev_risk = float(dev["dev_risk"])
    launch_path_risk = _launch_path_risk(token_ctx)

    raw_score = (
        0.24 * authority_risk
        + 0.26 * lp_risk
        + 0.22 * concentration_risk
        + 0.20 * dev_risk
        + 0.08 * launch_path_risk
    )
    rug_score = max(0.0, min(1.0, raw_score))

    flags = authority["authority_flags"] + lp["lp_flags"] + concentration["concentration_flags"] + dev["dev_flags"]
    warnings = lp["lp_warnings"] + dev["dev_warnings"]

    bundle_composition = str(token_ctx.get("bundle_composition_dominant") or "unknown").lower()
    retry_pattern = token_ctx.get("bundle_failure_retry_pattern")
    retry_count = int(retry_pattern) if isinstance(retry_pattern, (int, float)) else 0
    if bundle_composition == "sell-only":
        warnings.append("bundle_sell_only_flow")
    if retry_count >= 2:
        warnings.append("bundle_retry_pattern_severe")

    status = "ok"
    critical_missing = []
    for key in ("top1_holder_share", "top20_holder_share"):
        if key not in token_ctx:
            critical_missing.append(key)
    if "mint_authority" not in token_ctx and "freeze_authority" not in token_ctx:
        critical_missing.append("authority_data")
    if critical_missing:
        status = "partial"
        warnings.append(f"missing_critical_fields:{','.join(critical_missing)}")

    verdict = "PASS"
    if rug_score >= settings.RUG_IGNORE_THRESHOLD:
        verdict = "IGNORE"
    elif rug_score >= settings.RUG_WATCH_THRESHOLD:
        verdict = "WATCH"

    if (
        (not authority["mint_revoked"])
        or float(token_ctx.get("top1_holder_share") or 0.0) >= 0.30
        or (float(token_ctx.get("dev_sell_pressure_5m") or 0.0) >= settings.RUG_DEV_SELL_PRESSURE_HARD and float(token_ctx.get("dev_wallet_confidence_score", 1.0)) >= 0.5)
        or lp.get("lp_explicit_recoverable")
    ):
        verdict = "IGNORE"

    if status == "partial" and settings.RUG_ENGINE_FAILCLOSED and verdict == "PASS":
        verdict = "WATCH"

    return {
        "token_address": str(token_ctx.get("token_address") or ""),
        "symbol": str(token_ctx.get("symbol") or ""),
        "name": str(token_ctx.get("name") or ""),
        "mint_revoked": authority["mint_revoked"],
        "freeze_revoked": authority["freeze_revoked"],
        "lp_burn_confirmed": lp["lp_burn_confirmed"],
        "lp_burn_evidence_score": lp["lp_burn_evidence_score"],
        "lp_locked_flag": lp["lp_locked_flag"],
        "lp_lock_evidence_score": lp["lp_lock_evidence_score"],
        "lp_lock_provider_label": lp["lp_lock_provider_label"],
        "top1_holder_share": float(token_ctx.get("top1_holder_share") or 0.0),
        "top20_holder_share": float(token_ctx.get("top20_holder_share") or 0.0),
        "dev_sell_pressure_5m": float(token_ctx.get("dev_sell_pressure_5m") or 0.0),
        "rug_score": round(rug_score, 6),
        "rug_verdict": verdict,
        "rug_flags": sorted(set(flags)),
        "rug_warnings": sorted(set(warnings)),
        "rug_status": status,
        "assessed_at": utc_now_iso(),
        "contract_version": CONTRACT_VERSION,
    }
