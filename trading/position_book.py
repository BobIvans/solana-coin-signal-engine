"""Position book state transitions for paper trading."""

from __future__ import annotations

from typing import Any

from trading.pnl_engine import compute_exit_pnl, compute_unrealized_pnl
from utils.clock import utc_now_iso


def _next_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:04d}"


def ensure_state(state: dict[str, Any], settings: Any) -> dict[str, Any]:
    if "positions" not in state:
        state["positions"] = []
    if "portfolio" not in state:
        starting = float(settings.PAPER_STARTING_CAPITAL_SOL)
        state["portfolio"] = {
            "as_of": utc_now_iso(),
            "starting_capital_sol": starting,
            "free_capital_sol": starting,
            "capital_in_positions_sol": 0.0,
            "reserved_fees_sol": 0.0,
            "realized_pnl_sol": 0.0,
            "unrealized_pnl_sol": 0.0,
            "equity_sol": starting,
            "open_positions": 0,
            "closed_positions": 0,
            "contract_version": settings.PAPER_CONTRACT_VERSION,
        }
    state.setdefault("next_position_seq", 1)
    state.setdefault("next_trade_seq", 1)
    return state


def get_open_position_by_token(state: dict[str, Any], token_address: str) -> dict[str, Any] | None:
    for pos in state.get("positions", []):
        if pos.get("is_open") and pos.get("token_address") == token_address:
            return pos
    return None


def get_open_position_by_id(state: dict[str, Any], position_id: str) -> dict[str, Any] | None:
    for pos in state.get("positions", []):
        if pos.get("is_open") and pos.get("position_id") == position_id:
            return pos
    return None


def open_position(fill_ctx: dict[str, Any], signal_ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    position_id = _next_id("pos", int(state["next_position_seq"]))
    state["next_position_seq"] += 1
    now = utc_now_iso()

    position = {
        "position_id": position_id,
        "token_address": signal_ctx.get("token_address"),
        "symbol": signal_ctx.get("symbol"),
        "is_open": True,
        "entry_decision": signal_ctx.get("entry_decision"),
        "opened_at": now,
        "entry_price_usd": float(fill_ctx.get("executed_price_usd") or 0.0),
        "position_size_sol": float(fill_ctx.get("filled_notional_sol") or 0.0),
        "remaining_size_sol": float(fill_ctx.get("filled_notional_sol") or 0.0),
        "partial_1_taken": False,
        "partial_2_taken": False,
        "realized_pnl_sol": 0.0,
        "unrealized_pnl_sol": 0.0,
        "fees_paid_sol": float(fill_ctx.get("priority_fee_sol") or 0.0),
        "entry_snapshot": signal_ctx.get("entry_snapshot") or {},
        "last_mark_price_usd": float(fill_ctx.get("executed_price_usd") or 0.0),
        "last_updated_at": now,
        "contract_version": signal_ctx.get("contract_version"),
    }
    state["positions"].append(position)

    portfolio = state["portfolio"]
    portfolio["free_capital_sol"] -= position["position_size_sol"] + position["fees_paid_sol"]
    portfolio["capital_in_positions_sol"] += position["position_size_sol"]
    portfolio["reserved_fees_sol"] += position["fees_paid_sol"]
    portfolio["open_positions"] += 1
    portfolio["as_of"] = now
    return position


def apply_partial_exit(position_ctx: dict[str, Any], fill_ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    sold = float(fill_ctx.get("filled_notional_sol") or 0.0)
    requested = float(fill_ctx.get("requested_notional_sol") or 0.0)
    ratio = 0.0 if requested <= 0 else max(0.0, min(sold / requested, 1.0))
    cost_portion = float(position_ctx.get("remaining_size_sol") or 0.0) * ratio
    pnl = compute_exit_pnl(position_ctx, fill_ctx)

    position_ctx["remaining_size_sol"] = max(float(position_ctx.get("remaining_size_sol") or 0.0) - sold, 0.0)
    position_ctx["realized_pnl_sol"] = float(position_ctx.get("realized_pnl_sol") or 0.0) + pnl["realized_pnl_sol"]
    position_ctx["fees_paid_sol"] = float(position_ctx.get("fees_paid_sol") or 0.0) + pnl["fees_paid_sol"]
    position_ctx["last_mark_price_usd"] = float(fill_ctx.get("executed_price_usd") or position_ctx.get("last_mark_price_usd") or 0.0)
    position_ctx["last_updated_at"] = utc_now_iso()

    portfolio = state["portfolio"]
    portfolio["free_capital_sol"] += sold - pnl["fees_paid_sol"]
    portfolio["capital_in_positions_sol"] = max(float(portfolio.get("capital_in_positions_sol") or 0.0) - cost_portion, 0.0)
    portfolio["realized_pnl_sol"] = float(portfolio.get("realized_pnl_sol") or 0.0) + pnl["realized_pnl_sol"]
    portfolio["reserved_fees_sol"] = max(float(portfolio.get("reserved_fees_sol") or 0.0) - pnl["fees_paid_sol"], 0.0)

    if position_ctx["remaining_size_sol"] <= 1e-12:
        return close_position(position_ctx, fill_ctx, state)
    return position_ctx


def close_position(position_ctx: dict[str, Any], fill_ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    position_ctx["is_open"] = False
    position_ctx["remaining_size_sol"] = 0.0
    position_ctx["last_updated_at"] = utc_now_iso()
    portfolio = state["portfolio"]
    portfolio["open_positions"] = max(int(portfolio.get("open_positions") or 0) - 1, 0)
    portfolio["closed_positions"] = int(portfolio.get("closed_positions") or 0) + 1
    _ = fill_ctx
    return position_ctx


def mark_to_market(position_ctx: dict[str, Any], market_ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    pnl = compute_unrealized_pnl(position_ctx, market_ctx)
    position_ctx["unrealized_pnl_sol"] = pnl["unrealized_pnl_sol"]
    position_ctx["last_mark_price_usd"] = float(market_ctx.get("price_usd") or position_ctx.get("last_mark_price_usd") or 0.0)
    position_ctx["last_updated_at"] = utc_now_iso()

    portfolio = state["portfolio"]
    open_positions = [p for p in state.get("positions", []) if p.get("is_open")]
    portfolio["unrealized_pnl_sol"] = sum(float(p.get("unrealized_pnl_sol") or 0.0) for p in open_positions)
    portfolio["equity_sol"] = float(portfolio.get("starting_capital_sol") or 0.0) + float(portfolio.get("realized_pnl_sol") or 0.0) + float(portfolio.get("unrealized_pnl_sol") or 0.0)
    portfolio["as_of"] = utc_now_iso()
    return position_ctx


def next_trade_id(state: dict[str, Any]) -> str:
    trade_id = _next_id("tr", int(state["next_trade_seq"]))
    state["next_trade_seq"] += 1
    return trade_id
