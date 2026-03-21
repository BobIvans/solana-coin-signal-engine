"""Paper-trading friction models (slippage, fees, failure, partial fills)."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_sol_usd(market_ctx: dict[str, Any], settings: Any) -> float:
    raw = market_ctx.get("sol_usd")
    if raw not in (None, ""):
        try:
            value = float(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    fallback = getattr(settings, "PAPER_SOL_USD_FALLBACK", 100.0)
    try:
        value = float(fallback)
    except (TypeError, ValueError):
        value = 100.0
    return max(value, 1.0)


def _order_side(order_ctx: dict[str, Any]) -> str:
    explicit = str(order_ctx.get("side") or "").strip().lower()
    if explicit in {"buy", "sell"}:
        return explicit
    if order_ctx.get("exit_decision") or order_ctx.get("exit_fraction") is not None:
        return "sell"
    return "buy"


def _exit_flags(order_ctx: dict[str, Any], market_ctx: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for source in (order_ctx.get("exit_flags"), market_ctx.get("exit_flags")):
        if isinstance(source, list):
            values.update(str(item).strip() for item in source if str(item).strip())
    reason = str(order_ctx.get("exit_reason") or market_ctx.get("exit_reason") or "").strip()
    if reason:
        values.add(reason)
    return values


def _congestion_stress_multiplier(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    multiplier = max(_safe_float(market_ctx.get("congestion_multiplier"), 1.0), 1.0)
    if not bool(getattr(settings, "CONGESTION_STRESS_ENABLED", True)):
        return multiplier
    flags = _exit_flags(order_ctx, market_ctx)
    if "cluster_dump_detected" in flags:
        multiplier += 0.35
    if "linkage_risk_exit" in flags:
        multiplier += 0.20
    if "kill_switch_triggered" in flags:
        multiplier += 0.45
    if "shock_not_recovered_exit" in flags:
        multiplier += 0.25
    if str(order_ctx.get("exit_decision") or "").upper() == "FULL_EXIT":
        multiplier += 0.05
    return round(max(multiplier, 1.0), 6)


def compute_fill_realism(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    liquidity = max(_safe_float(market_ctx.get("liquidity_usd") or market_ctx.get("liquidity"), 1.0), 1.0)
    volatility = max(_safe_float(market_ctx.get("volatility") or market_ctx.get("volume_velocity"), 0.0), 0.0)
    requested_sol = max(_safe_float(order_ctx.get("requested_notional_sol"), 0.0), 0.0)
    requested_usd = requested_sol * _resolve_sol_usd(market_ctx, settings)
    participation = max(requested_usd / liquidity, 0.0)

    liquidity_sensitivity = _safe_float(getattr(settings, "PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY", 1.0), 1.0)
    default_slippage_bps = _safe_float(getattr(settings, "PAPER_DEFAULT_SLIPPAGE_BPS", 150.0), 150.0)
    max_slippage_bps = _safe_float(getattr(settings, "PAPER_MAX_SLIPPAGE_BPS", 1200.0), 1200.0)
    mode = str(getattr(settings, "FRICTION_MODEL_MODE", "amm_approx") or "amm_approx").strip().lower()
    exponent = max(_safe_float(getattr(settings, "PAPER_AMM_IMPACT_EXPONENT", 1.35), 1.35), 1.0)

    if mode == "linear":
        estimated_price_impact_bps = participation * 10_000 * liquidity_sensitivity
    else:
        estimated_price_impact_bps = (participation ** exponent) * 10_000 * liquidity_sensitivity

    side = _order_side(order_ctx)
    sell_pressure = max(
        _safe_float(
            market_ctx.get("sell_pressure")
            or market_ctx.get("cluster_sell_concentration_120s")
            or market_ctx.get("sell_pressure_ratio"),
            0.0,
        ),
        0.0,
    )
    if side == "sell":
        estimated_price_impact_bps *= 1.0 + min(sell_pressure, 1.0) * 0.6

    volatility_component = volatility * 20.0
    urgency_component = 50.0 if str(order_ctx.get("exit_decision") or "").upper() == "FULL_EXIT" else 0.0
    congestion_stress_multiplier = _congestion_stress_multiplier(order_ctx, market_ctx, settings)
    transfer_fee_bps = max(_safe_float(market_ctx.get("transfer_fee_bps"), 0.0), 0.0) if side == "sell" and market_ctx.get("transfer_fee_detected") else 0.0

    effective_slippage_bps = default_slippage_bps + (estimated_price_impact_bps + volatility_component + urgency_component) * congestion_stress_multiplier + transfer_fee_bps
    effective_slippage_bps = _clamp(effective_slippage_bps, 1.0, max_slippage_bps)

    if mode == "linear":
        realism_status = "linear_model"
    elif congestion_stress_multiplier > 1.0 or transfer_fee_bps > 0:
        realism_status = "amm_approx_stressed"
    else:
        realism_status = "amm_approx"

    return {
        "estimated_price_impact_bps": round(max(estimated_price_impact_bps, 0.0), 6),
        "congestion_stress_multiplier": congestion_stress_multiplier,
        "effective_slippage_bps": round(effective_slippage_bps, 6),
        "fill_realism_status": realism_status,
    }


def compute_slippage_bps(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    return float(compute_fill_realism(order_ctx, market_ctx, settings)["effective_slippage_bps"])


def compute_priority_fee_sol(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    congestion = float(market_ctx.get("congestion_multiplier") or 1.0)
    if market_ctx.get("priority_fee_avg_first_min"):
        congestion = max(congestion, float(market_ctx["priority_fee_avg_first_min"]))
    congestion = max(congestion, _congestion_stress_multiplier(order_ctx, market_ctx, settings))
    return max(float(getattr(settings, "PAPER_PRIORITY_FEE_BASE_SOL", 0.00002)) * max(congestion, 1.0), 0.0)


def compute_failed_tx_probability(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    liquidity = float(market_ctx.get("liquidity_usd") or market_ctx.get("liquidity") or 0.0)
    volatility = float(market_ctx.get("volatility") or market_ctx.get("volume_velocity") or 0.0)
    confidence = float(order_ctx.get("entry_confidence") or order_ctx.get("signal_quality") or 1.0)

    prob = float(getattr(settings, "PAPER_FAILED_TX_BASE_PROB", 0.03))
    if liquidity < 25_000:
        prob += float(getattr(settings, "PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON", 0.05))
    if volatility > 2.5:
        prob += float(getattr(settings, "PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON", 0.04))
    if confidence < 0.5:
        prob += 0.03

    return _clamp(prob, 0.0, 1.0)


def compute_partial_fill_ratio(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    if not bool(getattr(settings, "PAPER_PARTIAL_FILL_ALLOWED", True)):
        return 1.0

    liquidity = max(float(market_ctx.get("liquidity_usd") or 1.0), 1.0)
    requested_sol = max(float(order_ctx.get("requested_notional_sol") or 0.0), 0.0)
    requested_usd = requested_sol * _resolve_sol_usd(market_ctx, settings)
    pressure = requested_usd / liquidity
    volatility = max(float(market_ctx.get("volatility") or market_ctx.get("volume_velocity") or 0.0), 0.0)
    mode = str(getattr(settings, "FRICTION_MODEL_MODE", "amm_approx") or "amm_approx").strip().lower()

    if mode == "linear":
        raw_ratio = 1.0 - pressure * 0.8 - min(volatility * 0.05, 0.35)
    else:
        raw_ratio = 1.0 - min(pressure ** 1.2 * 1.1, 0.7) - min(volatility * 0.05, 0.35)

    min_ratio = float(getattr(settings, "PAPER_PARTIAL_FILL_MIN_RATIO", 0.5))
    if raw_ratio >= 1.0:
        return 1.0
    return _clamp(raw_ratio, min_ratio, 1.0)
