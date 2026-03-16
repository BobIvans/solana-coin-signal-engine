"""Runner for one paper trading cycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import Settings, load_settings
from trading.paper_trader import process_entry_signals, process_exit_signals, run_mark_to_market
from trading.position_book import ensure_state
from utils.io import read_json, write_json


def _default_paths(settings: Settings) -> dict[str, Path]:
    return {
        "entry": settings.PROCESSED_DATA_DIR / "entry_candidates.json",
        "exit": settings.PROCESSED_DATA_DIR / "exit_decisions.json",
        "market": settings.PROCESSED_DATA_DIR / "market_states.json",
        "positions": settings.PROCESSED_DATA_DIR / "positions.json",
        "portfolio": settings.PROCESSED_DATA_DIR / "portfolio_state.json",
        "signals": settings.PROCESSED_DATA_DIR / "signals.jsonl",
        "trades": settings.PROCESSED_DATA_DIR / "trades.jsonl",
    }


def run_paper_cycle(settings: Settings) -> dict[str, Any]:
    paths = _default_paths(settings)
    state: dict[str, Any] = read_json(paths["positions"], default={}) or {}
    state["paths"] = {"signals": paths["signals"], "trades": paths["trades"]}
    loaded_portfolio = read_json(paths["portfolio"], default=None)
    if loaded_portfolio is not None:
        state["portfolio"] = loaded_portfolio
    ensure_state(state, settings)

    entry_signals = read_json(paths["entry"], default=[]) or []
    exit_signals = read_json(paths["exit"], default=[]) or []
    market_states = read_json(paths["market"], default=[]) or []

    process_exit_signals(exit_signals, market_states, state, settings)
    process_entry_signals(entry_signals, market_states, state, settings)
    run_mark_to_market(state, market_states, settings)

    write_json(paths["positions"], {
        "positions": state.get("positions", []),
        "next_position_seq": state.get("next_position_seq", 1),
        "next_trade_seq": state.get("next_trade_seq", 1),
    })
    write_json(paths["portfolio"], state.get("portfolio", {}))
    return state


if __name__ == "__main__":
    run_paper_cycle(load_settings())
