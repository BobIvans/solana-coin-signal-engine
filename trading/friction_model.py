"""Paper-trading friction models (slippage, fees, failure, partial fills)."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_slippage_bps(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    liquidity = max(float(market_ctx.get("liquidity_usd") or market_ctx.get("liquidity") or 1.0), 1.0)
    volatility = max(float(market_ctx.get("volatility") or market_ctx.get("volume_velocity") or 0.0), 0.0)
    requested_sol = max(float(order_ctx.get("requested_notional_sol") or 0.0), 0.0)
    ref_price = max(float(order_ctx.get("reference_price_usd") or market_ctx.get("price_usd") or 0.0), 0.0)
    requested_usd = requested_sol * (market_ctx.get("sol_usd") or 100.0)

    liquidity_impact = 0.0 if liquidity <= 0 else (requested_usd / liquidity) * 10_000 * float(settings.PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY)
    volatility_component = volatility * 20.0
    urgency_component = 50.0 if str(order_ctx.get("exit_decision") or "") == "FULL_EXIT" else 0.0

    slippage_bps = float(settings.PAPER_DEFAULT_SLIPPAGE_BPS) + liquidity_impact + volatility_component + urgency_component
    _ = ref_price  # reserved for later price-sensitive models
    return _clamp(slippage_bps, 1.0, float(settings.PAPER_MAX_SLIPPAGE_BPS))


def compute_priority_fee_sol(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    congestion = float(market_ctx.get("congestion_multiplier") or 1.0)
    if market_ctx.get("priority_fee_avg_first_min"):
        congestion = max(congestion, float(market_ctx["priority_fee_avg_first_min"]))
    _ = order_ctx
    return max(float(settings.PAPER_PRIORITY_FEE_BASE_SOL) * max(congestion, 1.0), 0.0)


def compute_failed_tx_probability(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    liquidity = float(market_ctx.get("liquidity_usd") or market_ctx.get("liquidity") or 0.0)
    volatility = float(market_ctx.get("volatility") or market_ctx.get("volume_velocity") or 0.0)
    confidence = float(order_ctx.get("entry_confidence") or order_ctx.get("signal_quality") or 1.0)

    prob = float(settings.PAPER_FAILED_TX_BASE_PROB)
    if liquidity < 25_000:
        prob += float(settings.PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON)
    if volatility > 2.5:
        prob += float(settings.PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON)
    if confidence < 0.5:
        prob += 0.03

    return _clamp(prob, 0.0, 1.0)


def compute_partial_fill_ratio(order_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> float:
    if not bool(settings.PAPER_PARTIAL_FILL_ALLOWED):
        return 1.0

    liquidity = max(float(market_ctx.get("liquidity_usd") or 1.0), 1.0)
    requested_sol = max(float(order_ctx.get("requested_notional_sol") or 0.0), 0.0)
    requested_usd = requested_sol * (market_ctx.get("sol_usd") or 100.0)
    pressure = requested_usd / liquidity
    volatility = max(float(market_ctx.get("volatility") or market_ctx.get("volume_velocity") or 0.0), 0.0)

    raw_ratio = 1.0 - pressure * 0.8 - min(volatility * 0.05, 0.35)
    min_ratio = float(settings.PAPER_PARTIAL_FILL_MIN_RATIO)
    if raw_ratio >= 1.0:
        return 1.0
    return _clamp(raw_ratio, min_ratio, 1.0)
