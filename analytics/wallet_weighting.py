"""Canonical wallet weighting helpers for unified score."""

from __future__ import annotations

from typing import Any, Mapping

DEFAULT_WALLET_WEIGHTING_MODE = "shadow"
WALLET_WEIGHTING_MODES = {"off", "shadow", "on"}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in {"true", "yes", "y"}:
            return 1.0
        if text in {"false", "no", "n"}:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _first_present(token: Mapping[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in token and token[key] is not None:
            return token[key]
    return default


def _normalize_fraction(value: float, *, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return _clip(value / max_value, 0.0, 1.0)


def _confidence_strength(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text == "high":
        return 1.0
    if text == "medium":
        return 0.5
    if text == "low":
        return 0.15
    return 0.0


def normalize_wallet_weighting_mode(explicit_mode: str | None, settings: Any) -> str:
    mode = str(explicit_mode or getattr(settings, "WALLET_WEIGHTING_MODE", DEFAULT_WALLET_WEIGHTING_MODE)).strip().lower()
    if mode not in WALLET_WEIGHTING_MODES:
        return DEFAULT_WALLET_WEIGHTING_MODE
    return mode


def extract_wallet_weighting_inputs(token_ctx: Mapping[str, Any]) -> dict[str, Any]:
    wallet_features = token_ctx.get("wallet_features")
    if not isinstance(wallet_features, Mapping):
        wallet_features = {}

    def pick(*keys: str, default: Any = None) -> Any:
        value = _first_present(token_ctx, keys, None)
        if value is not None:
            return value
        return _first_present(wallet_features, keys, default)

    return {
        "wallet_registry_status": str(pick("wallet_registry_status", default="missing") or "missing").lower(),
        "smart_wallet_score_sum": max(_as_float(pick("smart_wallet_score_sum", default=0.0), 0.0), 0.0),
        "smart_wallet_tier1_hits": int(_as_float(pick("smart_wallet_tier1_hits", default=0.0), 0.0)),
        "smart_wallet_tier2_hits": int(_as_float(pick("smart_wallet_tier2_hits", default=0.0), 0.0)),
        "smart_wallet_tier3_hits": int(_as_float(pick("smart_wallet_tier3_hits", default=0.0), 0.0)),
        "smart_wallet_early_entry_hits": int(_as_float(pick("smart_wallet_early_entry_hits", default=0.0), 0.0)),
        "smart_wallet_active_hits": int(_as_float(pick("smart_wallet_active_hits", default=0.0), 0.0)),
        "smart_wallet_watch_hits": int(_as_float(pick("smart_wallet_watch_hits", default=0.0), 0.0)),
        "smart_wallet_conviction_bonus": max(_as_float(pick("smart_wallet_conviction_bonus", default=0.0), 0.0), 0.0),
        "smart_wallet_registry_confidence": pick("smart_wallet_registry_confidence", default=None),
        "smart_wallet_netflow_bias": pick("smart_wallet_netflow_bias", default=None),
    }


def _wallet_cap_from_hits(wallet_inputs: Mapping[str, Any], settings: Any) -> float:
    tier1_hits = int(wallet_inputs.get("smart_wallet_tier1_hits") or 0)
    tier2_hits = int(wallet_inputs.get("smart_wallet_tier2_hits") or 0)
    tier3_hits = int(wallet_inputs.get("smart_wallet_tier3_hits") or 0)
    active_hits = int(wallet_inputs.get("smart_wallet_active_hits") or 0)
    watch_hits = int(wallet_inputs.get("smart_wallet_watch_hits") or 0)
    if tier1_hits > 0 and active_hits > 0:
        return float(getattr(settings, "WALLET_WEIGHTING_CAP_TIER1", 8.0))
    if tier2_hits > 0 and active_hits > 0:
        return float(getattr(settings, "WALLET_WEIGHTING_CAP_TIER2", 5.0))
    if tier3_hits > 0 and active_hits > 0:
        return float(getattr(settings, "WALLET_WEIGHTING_CAP_TIER3", 3.0))
    if watch_hits > 0:
        return float(getattr(settings, "WALLET_WEIGHTING_CAP_WATCH_ONLY", 1.0))
    return 0.0


def compute_wallet_weighting(
    token_ctx: Mapping[str, Any],
    settings: Any,
    requested_mode: str | None,
) -> dict[str, Any]:
    wallet_inputs = extract_wallet_weighting_inputs(token_ctx)
    normalized_mode = normalize_wallet_weighting_mode(requested_mode, settings)
    registry_status = str(wallet_inputs.get("wallet_registry_status") or "missing").lower()

    score_sum = float(wallet_inputs.get("smart_wallet_score_sum") or 0.0)
    tier1_hits = int(wallet_inputs.get("smart_wallet_tier1_hits") or 0)
    tier2_hits = int(wallet_inputs.get("smart_wallet_tier2_hits") or 0)
    tier3_hits = int(wallet_inputs.get("smart_wallet_tier3_hits") or 0)
    early_hits = int(wallet_inputs.get("smart_wallet_early_entry_hits") or 0)
    active_hits = int(wallet_inputs.get("smart_wallet_active_hits") or 0)
    watch_hits = int(wallet_inputs.get("smart_wallet_watch_hits") or 0)
    conviction_bonus = float(wallet_inputs.get("smart_wallet_conviction_bonus") or 0.0)
    registry_confidence = wallet_inputs.get("smart_wallet_registry_confidence")
    netflow_bias = wallet_inputs.get("smart_wallet_netflow_bias")

    explain = {
        "smart_wallet_score_sum": _round(score_sum),
        "smart_wallet_tier1_hits": tier1_hits,
        "smart_wallet_tier2_hits": tier2_hits,
        "smart_wallet_tier3_hits": tier3_hits,
        "smart_wallet_early_entry_hits": early_hits,
        "smart_wallet_active_hits": active_hits,
        "smart_wallet_watch_hits": watch_hits,
        "smart_wallet_conviction_bonus": _round(conviction_bonus),
        "smart_wallet_registry_confidence": registry_confidence,
        "wallet_adjustment_cap": 0.0,
        "degraded_wallet_registry": registry_status != "validated",
        "smart_wallet_netflow_bias": netflow_bias,
    }

    if normalized_mode == "off":
        return {
            "wallet_weighting_mode": normalized_mode,
            "wallet_weighting_effective_mode": "off",
            "wallet_registry_status": registry_status,
            "wallet_score_component_raw": 0.0,
            "wallet_score_component_applied": 0.0,
            "wallet_score_component_applied_shadow": 0.0,
            "wallet_score_component_capped": False,
            "wallet_score_component_reason": "wallet weighting disabled",
            "wallet_score_explain": explain,
        }

    if registry_status != "validated":
        return {
            "wallet_weighting_mode": normalized_mode,
            "wallet_weighting_effective_mode": "degraded_zero",
            "wallet_registry_status": registry_status,
            "wallet_score_component_raw": 0.0,
            "wallet_score_component_applied": 0.0,
            "wallet_score_component_applied_shadow": 0.0,
            "wallet_score_component_capped": False,
            "wallet_score_component_reason": f"wallet registry status={registry_status}; wallet adjustment forced to zero",
            "wallet_score_explain": explain,
        }

    normalized_sum = _normalize_fraction(
        score_sum,
        max_value=float(getattr(settings, "WALLET_WEIGHTING_SCORE_SUM_MAX", 20.0)),
    )
    tier_weighted_hits = (3.0 * tier1_hits) + (1.75 * tier2_hits) + (0.75 * tier3_hits)
    tier_hit_strength = _normalize_fraction(
        tier_weighted_hits,
        max_value=float(getattr(settings, "WALLET_WEIGHTING_TIER_HIT_STRENGTH_MAX", 6.0)),
    )
    early_entry_strength = _normalize_fraction(
        float(early_hits),
        max_value=float(getattr(settings, "WALLET_WEIGHTING_EARLY_ENTRY_MAX", 2.0)),
    )
    conviction_bonus_strength = _normalize_fraction(
        conviction_bonus,
        max_value=float(getattr(settings, "WALLET_WEIGHTING_CONVICTION_MAX", 3.0)),
    )
    confidence_strength = _confidence_strength(registry_confidence)

    raw_unit = (
        (0.40 * normalized_sum)
        + (0.20 * tier_hit_strength)
        + (0.15 * early_entry_strength)
        + (0.15 * conviction_bonus_strength)
        + (0.10 * confidence_strength)
    )
    cap = _wallet_cap_from_hits(wallet_inputs, settings)
    applied_shadow = _round(min(raw_unit * cap, cap)) if cap > 0 else 0.0
    capped = cap > 0 and raw_unit * cap > cap
    applied = applied_shadow if normalized_mode == "on" else 0.0

    reason = (
        "wallet evidence scored from validated enrichment; "
        f"tier_hits=({tier1_hits},{tier2_hits},{tier3_hits}), active_hits={active_hits}, watch_hits={watch_hits}, "
        f"confidence={registry_confidence or 'missing'}"
    )
    if watch_hits > 0 and active_hits <= 0 and tier1_hits <= 0 and tier2_hits <= 0 and tier3_hits <= 0:
        reason = "watch-only wallet evidence receives minimal capped impact"

    explain["wallet_adjustment_cap"] = _round(cap)
    return {
        "wallet_weighting_mode": normalized_mode,
        "wallet_weighting_effective_mode": normalized_mode,
        "wallet_registry_status": registry_status,
        "wallet_score_component_raw": _round(raw_unit),
        "wallet_score_component_applied": _round(applied),
        "wallet_score_component_applied_shadow": _round(applied_shadow),
        "wallet_score_component_capped": capped,
        "wallet_score_component_reason": reason,
        "wallet_score_explain": explain,
    }


def build_wallet_adjustment_compat(wallet_weighting: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "requested_mode": wallet_weighting.get("wallet_weighting_mode"),
        "effective_mode": wallet_weighting.get("wallet_weighting_effective_mode"),
        "registry_status": wallet_weighting.get("wallet_registry_status"),
        "registry_degraded": wallet_weighting.get("wallet_weighting_effective_mode") == "degraded_zero",
        "raw_delta": _round(_as_float(wallet_weighting.get("wallet_score_component_raw"), 0.0)),
        "applied_delta": _round(_as_float(wallet_weighting.get("wallet_score_component_applied"), 0.0)),
        "shadow_delta": _round(_as_float(wallet_weighting.get("wallet_score_component_applied_shadow"), 0.0)),
        "capped": bool(wallet_weighting.get("wallet_score_component_capped")),
        "reason": wallet_weighting.get("wallet_score_component_reason"),
        "explain": dict(wallet_weighting.get("wallet_score_explain") or {}),
    }
