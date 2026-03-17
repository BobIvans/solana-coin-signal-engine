from __future__ import annotations

from datetime import datetime, timezone


def roll_daily_state_if_needed(state: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    if state.get("current_day") != day:
        state["current_day"] = day
        state.setdefault("counters", {})["trades_today"] = 0
        state.setdefault("counters", {})["pnl_pct_today"] = 0.0
        state["consecutive_losses"] = 0
    return state


def update_trade_counters(state: dict, pnl_pct: float = 0.0) -> dict:
    counters = state.setdefault("counters", {})
    counters["trades_today"] = int(counters.get("trades_today", 0)) + 1
    counters["pnl_pct_today"] = float(counters.get("pnl_pct_today", 0.0)) + float(pnl_pct)
    return state


def update_loss_streak(state: dict, pnl_pct: float) -> dict:
    if pnl_pct < 0:
        state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
    else:
        state["consecutive_losses"] = 0
    return state
