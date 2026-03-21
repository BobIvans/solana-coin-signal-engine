from __future__ import annotations

from datetime import datetime, timezone


def roll_daily_state_if_needed(state: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    if state.get("current_day") != day:
        state["current_day"] = day
        counters = state.setdefault("counters", {})
        counters["trades_today"] = 0
        counters["pnl_pct_today"] = 0.0
        counters["realized_pnl_sol_today"] = 0.0
        counters["starting_capital_sol"] = float(counters.get("starting_capital_sol") or state.get("starting_capital_sol") or 0.0)
        state["consecutive_losses"] = 0
    return state


def update_trade_counters(
    state: dict,
    pnl_pct: float = 0.0,
    *,
    realized_pnl_sol: float = 0.0,
    starting_capital_sol: float | None = None,
) -> dict:
    counters = state.setdefault("counters", {})
    counters["trades_today"] = int(counters.get("trades_today", 0)) + 1
    counters["pnl_pct_today"] = float(counters.get("pnl_pct_today", 0.0)) + float(pnl_pct)
    counters["realized_pnl_sol_today"] = float(counters.get("realized_pnl_sol_today", 0.0)) + float(realized_pnl_sol)
    if starting_capital_sol is not None:
        counters["starting_capital_sol"] = float(starting_capital_sol)
    else:
        counters.setdefault("starting_capital_sol", float(state.get("starting_capital_sol") or 0.0))
    return state


def update_loss_streak(state: dict, pnl_pct: float) -> dict:
    if pnl_pct < 0:
        state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
    else:
        state["consecutive_losses"] = 0
    return state
