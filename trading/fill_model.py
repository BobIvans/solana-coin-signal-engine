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


def _build_result(
    requested: float,
    filled: float,
    ref_price: float,
    exec_price: float,
    slippage_bps: float,
    priority_fee_sol: float,
    tx_failed: bool,
    failure_reason: str | None,
    *,
    fill_ratio: float | None = None,
    requested_cost_basis_sol: float | None = None,
    filled_cost_basis_sol: float | None = None,
    execution_assumption: str = "observed_market_price",
    degraded_execution_path: bool = False,
) -> dict[str, Any]:
    ratio = 0.0 if requested <= 0 else max(0.0, min((fill_ratio if fill_ratio is not None else filled / requested), 1.0))
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
        "requested_cost_basis_sol": 0.0 if tx_failed else float(requested_cost_basis_sol if requested_cost_basis_sol is not None else requested),
        "filled_cost_basis_sol": 0.0 if tx_failed else float(filled_cost_basis_sol if filled_cost_basis_sol is not None else filled),
        "execution_assumption": execution_assumption,
        "degraded_execution_path": bool(degraded_execution_path and not tx_failed),
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


def _is_failclosed_exit(exit_ctx: dict[str, Any]) -> bool:
    warnings = {str(item) for item in (exit_ctx.get("exit_warnings") or [])}
    flags = {str(item) for item in (exit_ctx.get("exit_flags") or [])}
    return (
        str(exit_ctx.get("exit_reason") or "") == "missing_current_state_failclosed"
        or "failclosed_missing_fields" in flags
        or any(item.startswith("missing_critical_") for item in warnings)
    )


def _failclosed_reference_price(position_ctx: dict[str, Any], settings: Any) -> float:
    entry_price = float(position_ctx.get("entry_price_usd") or 0.0)
    regime = str(position_ctx.get("entry_decision") or "SCALP").upper()
    if regime == "TREND":
        stop_pct = float(getattr(settings, "EXIT_TREND_HARD_STOP_PCT", -18.0))
    else:
        stop_pct = float(getattr(settings, "EXIT_SCALP_STOP_LOSS_PCT", -10.0))
    return max(entry_price * max(0.0, 1.0 + stop_pct / 100.0), 0.0)


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
    return _build_result(
        requested,
        filled,
        reference_price,
        exec_price,
        slippage_bps,
        priority_fee_sol,
        False,
        None,
        fill_ratio=partial_ratio,
    )


def simulate_exit_fill(position_ctx: dict[str, Any], exit_ctx: dict[str, Any], market_ctx: dict[str, Any], settings: Any) -> dict[str, Any]:
    remaining = max(float(position_ctx.get("remaining_size_sol") or 0.0), 0.0)
    fraction = max(0.0, min(float(exit_ctx.get("exit_fraction") or 1.0), 1.0))
    requested = remaining * fraction

    exit_snapshot = dict(exit_ctx.get("exit_snapshot") or {})
    observed_reference_price = float(
        exit_snapshot.get("price_usd")
        or market_ctx.get("price_usd")
        or position_ctx.get("last_mark_price_usd")
        or 0.0
    )
    failclosed_exit = _is_failclosed_exit(exit_ctx)
    if observed_reference_price > 0:
        reference_price = observed_reference_price
        execution_assumption = "observed_market_price"
        degraded_execution_path = False
    elif failclosed_exit:
        reference_price = _failclosed_reference_price(position_ctx, settings)
        execution_assumption = "failclosed_pessimistic_price"
        degraded_execution_path = True
    else:
        reference_price = float(position_ctx.get("entry_price_usd") or 0.0)
        execution_assumption = "entry_price_fallback"
        degraded_execution_path = True

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
    filled_cost_basis = requested * partial_ratio
    exec_price = reference_price * (1 - slippage_bps / 10_000)
    entry_price = float(position_ctx.get("entry_price_usd") or reference_price or 0.0)
    price_ratio = 0.0 if entry_price <= 0 else max(exec_price, 0.0) / entry_price
    proceeds_sol = filled_cost_basis * price_ratio
    return _build_result(
        requested,
        proceeds_sol,
        reference_price,
        exec_price,
        slippage_bps,
        priority_fee_sol,
        False,
        None,
        fill_ratio=partial_ratio,
        requested_cost_basis_sol=requested,
        filled_cost_basis_sol=filled_cost_basis,
        execution_assumption=execution_assumption,
        degraded_execution_path=degraded_execution_path,
    )
