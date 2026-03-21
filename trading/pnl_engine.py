"""PnL math for paper-trading fills and positions."""

from __future__ import annotations

from typing import Any


def _clamp_fraction(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def compute_closed_fraction_of_position(position_ctx: dict[str, Any], fill_ctx: dict[str, Any]) -> float:
    """Return the fraction of the remaining position cost basis that was actually closed."""
    remaining_before = float(position_ctx.get("remaining_size_sol") or 0.0)
    requested_cost_basis = float(fill_ctx.get("requested_cost_basis_sol") or fill_ctx.get("requested_notional_sol") or 0.0)
    filled_cost_basis = float(fill_ctx.get("filled_cost_basis_sol") or 0.0)
    if filled_cost_basis <= 0.0:
        fill_ratio = float(fill_ctx.get("fill_ratio") or 0.0)
        if requested_cost_basis > 0.0 and fill_ratio > 0.0:
            filled_cost_basis = requested_cost_basis * _clamp_fraction(fill_ratio)
        else:
            filled_notional = float(fill_ctx.get("filled_notional_sol") or 0.0)
            filled_cost_basis = min(filled_notional, requested_cost_basis)

    if remaining_before <= 0.0 or requested_cost_basis <= 0.0 or filled_cost_basis <= 0.0:
        return 0.0

    fill_ratio = _clamp_fraction(filled_cost_basis / requested_cost_basis)
    requested_fraction = _clamp_fraction(requested_cost_basis / remaining_before)
    return _clamp_fraction(requested_fraction * fill_ratio)


def compute_entry_costs(fill_ctx: dict[str, Any]) -> dict[str, float]:
    filled = float(fill_ctx.get("filled_notional_sol") or 0.0)
    fee = float(fill_ctx.get("priority_fee_sol") or 0.0)
    gross = -(filled + fee)
    return {
        "gross_pnl_sol": gross,
        "net_pnl_sol": gross,
        "fees_paid_sol": fee,
        "capital_used_sol": filled,
    }


def compute_exit_pnl(position_ctx: dict[str, Any], fill_ctx: dict[str, Any]) -> dict[str, float]:
    sold_notional = float(fill_ctx.get("filled_notional_sol") or 0.0)
    closed_fraction = compute_closed_fraction_of_position(position_ctx, fill_ctx)
    cost_basis = float(position_ctx.get("remaining_size_sol") or 0.0) * closed_fraction
    gross = sold_notional - cost_basis
    fee = float(fill_ctx.get("priority_fee_sol") or 0.0)
    net = gross - fee
    return {
        "gross_pnl_sol": gross,
        "net_pnl_sol": net,
        "realized_pnl_sol": net,
        "fees_paid_sol": fee,
        "cost_basis_consumed_sol": cost_basis,
        "sold_notional_sol": sold_notional,
        "closed_fraction_of_position": closed_fraction,
    }


def compute_unrealized_pnl(position_ctx: dict[str, Any], market_ctx: dict[str, Any]) -> dict[str, float]:
    remaining_sol = float(position_ctx.get("remaining_size_sol") or 0.0)
    entry_price = float(position_ctx.get("entry_price_usd") or 0.0)
    mark_price = float(market_ctx.get("price_usd") or position_ctx.get("last_mark_price_usd") or entry_price)
    if entry_price <= 0:
        return {"unrealized_pnl_sol": 0.0}
    pnl_ratio = (mark_price - entry_price) / entry_price
    return {"unrealized_pnl_sol": remaining_sol * pnl_ratio}
