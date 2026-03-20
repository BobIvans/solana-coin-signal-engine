"""PnL math for paper-trading fills and positions."""

from __future__ import annotations

from typing import Any


def _clamp_fraction(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def compute_closed_fraction_of_position(position_ctx: dict[str, Any], fill_ctx: dict[str, Any]) -> float:
    """Return the fraction of the remaining position that was actually closed."""
    remaining_before = float(position_ctx.get("remaining_size_sol") or 0.0)
    requested = float(fill_ctx.get("requested_notional_sol") or 0.0)
    filled = float(fill_ctx.get("filled_notional_sol") or 0.0)

    if remaining_before <= 0.0 or requested <= 0.0 or filled <= 0.0:
        return 0.0

    fill_ratio = _clamp_fraction(filled / requested)
    requested_fraction = _clamp_fraction(requested / remaining_before)
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
