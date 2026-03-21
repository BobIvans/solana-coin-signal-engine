"""Turn entry/exit signals into deterministic simulated fills."""

from __future__ import annotations

import hashlib
from typing import Any

from trading.friction_model import (
    compute_failed_tx_probability,
    compute_partial_fill_ratio,
    compute_priority_fee_sol,
    compute_slippage_bps,
)


def _deterministic_uniform(key: str) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16) / float(0xFFFFFFFFFFFFFFFF)


def _build_result(requested: float, filled: float, ref_price: float, exec_price: float, slippage_bps: float, priority_fee_sol: float, tx_failed: bool, failure_reason: str | None) -> dict[str, Any]:
    ratio = 0.0 if requested <= 0 else max(0.0, min(filled / requested, 1.0))
    outcome = "failed_fill" if tx_failed else ("full_fill" if ratio >= 0.9999 else "partial_fill")
    return {
        "requested_notional_sol": requested,
        "filled_notional_sol": 0.0 if tx_failed else filled,
        "fill_ratio": 0.0 if tx_failed else ratio,
        "reference_price_usd": ref_price,
        "executed_price_usd": 0.0 if tx_failed else exec_price,
        "slippage_bps": slippage_bps,
        "priority_fee_sol": priority_fee_sol,
        "tx_failed": tx_failed,
        "failure_reason": failure_reason,
        "fill_outcome": outcome,
    }


def _effective_entry_position_pct(signal_ctx: dict[str, Any]) -> float:
    for field in ("effective_position_pct", "recommended_position_pct"):
        try:
            value = float(signal_ctx.get(field) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def simulate_entry_fill(signal_ctx: dict[str, Any], market_ctx: dict[str, Any], portfolio_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    free_capital = float(portfolio_ctx.get("free_capital_sol") or 0.0)
    requested = max(
        0.0,
        min(free_capital * _effective_entry_position_pct(signal_ctx), free_capital),
    )
    reference_price = float(market_ctx.get("price_usd") or signal_ctx.get("entry_snapshot", {}).get("price_usd") or 0.0)
    order_ctx = {
        "requested_notional_sol": requested,
        "reference_price_usd": reference_price,
        "entry_confidence": signal_ctx.get("entry_confidence", 1.0),
    }
    slippage_bps = compute_slippage_bps(order_ctx, market_ctx, settings)
    priority_fee_sol = compute_priority_fee_sol(order_ctx, market_ctx, settings)
    fail_prob = compute_failed_tx_probability(order_ctx, market_ctx, settings)

    draw = _deterministic_uniform(f"entry|{signal_ctx.get('token_address')}|{requested:.8f}|{reference_price:.12f}")
    if draw < fail_prob or requested <= 0:
        return _build_result(requested, 0.0, reference_price, 0.0, slippage_bps, priority_fee_sol, True, "simulated_low_liquidity_failure")

    partial_ratio = compute_partial_fill_ratio(order_ctx, market_ctx, settings)
    filled = requested * partial_ratio
    exec_price = reference_price * (1 + slippage_bps / 10_000)
    return _build_result(requested, filled, reference_price, exec_price, slippage_bps, priority_fee_sol, False, None)


def simulate_exit_fill(position_ctx: dict[str, Any], exit_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    remaining = max(float(position_ctx.get("remaining_size_sol") or 0.0), 0.0)
    fraction = max(0.0, min(float(exit_ctx.get("exit_fraction") or 1.0), 1.0))
    requested = remaining * fraction
    reference_price = float(exit_ctx.get("exit_snapshot", {}).get("price_usd") or market_ctx.get("price_usd") or position_ctx.get("last_mark_price_usd") or position_ctx.get("entry_price_usd") or 0.0)

    order_ctx = {
        "requested_notional_sol": requested,
        "reference_price_usd": reference_price,
        "exit_decision": exit_ctx.get("exit_decision"),
        "signal_quality": exit_ctx.get("signal_quality", 1.0),
    }
    slippage_bps = compute_slippage_bps(order_ctx, market_ctx, settings)
    priority_fee_sol = compute_priority_fee_sol(order_ctx, market_ctx, settings)
    fail_prob = compute_failed_tx_probability(order_ctx, market_ctx, settings)
    draw = _deterministic_uniform(f"exit|{position_ctx.get('position_id')}|{requested:.8f}|{reference_price:.12f}")

    if draw < fail_prob or requested <= 0:
        return _build_result(requested, 0.0, reference_price, 0.0, slippage_bps, priority_fee_sol, True, "simulated_exit_failure")

    partial_ratio = compute_partial_fill_ratio(order_ctx, market_ctx, settings)
    filled = requested * partial_ratio
    exec_price = reference_price * (1 - slippage_bps / 10_000)
    return _build_result(requested, filled, reference_price, exec_price, slippage_bps, priority_fee_sol, False, None)
