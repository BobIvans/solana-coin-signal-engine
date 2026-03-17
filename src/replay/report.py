from __future__ import annotations

import statistics
from typing import Any

from .io import write_markdown
from utils.io import write_json


def build_summary(signals: list[dict[str, Any]], trades: list[dict[str, Any]], *, wallet_weighting_mode: str, x_mode: str) -> dict[str, Any]:
    pnl = [float(t.get("pnl_pct", 0.0)) for t in trades]
    holds = [int(t.get("hold_sec", 0)) for t in trades]
    wins = [v for v in pnl if v > 0]
    exits: dict[str, int] = {}
    regimes: dict[str, int] = {}
    for t in trades:
        exits[t["exit_reason"]] = exits.get(t["exit_reason"], 0) + 1
        regimes[t["regime"]] = regimes.get(t["regime"], 0) + 1
    return {
        "total_signals": len(signals),
        "total_entries": sum(1 for s in signals if s.get("decision") == "ENTER"),
        "total_trades": len(trades),
        "winrate": round((len(wins) / len(trades)) if trades else 0.0, 6),
        "median_pnl_pct": round(statistics.median(pnl), 6) if pnl else 0.0,
        "avg_pnl_pct": round((sum(pnl) / len(pnl)) if pnl else 0.0, 6),
        "avg_hold_sec": round((sum(holds) / len(holds)) if holds else 0.0, 6),
        "best_trade": max(trades, key=lambda t: float(t.get("pnl_pct", 0.0)), default=None),
        "worst_trade": min(trades, key=lambda t: float(t.get("pnl_pct", 0.0)), default=None),
        "exit_reason_breakdown": exits,
        "regime_breakdown": regimes,
        "wallet_weighting_mode": wallet_weighting_mode,
        "x_mode": x_mode,
    }


def write_summary_json(path: str, summary: dict[str, Any]) -> None:
    write_json(path, summary)


def write_summary_md(path: str, summary: dict[str, Any]) -> None:
    lines = [
        "# Replay Summary",
        f"- total_signals: {summary['total_signals']}",
        f"- total_trades: {summary['total_trades']}",
        f"- winrate: {summary['winrate']}",
        f"- avg_pnl_pct: {summary['avg_pnl_pct']}",
        f"- wallet_weighting_mode: {summary['wallet_weighting_mode']}",
        f"- x_mode: {summary['x_mode']}",
    ]
    write_markdown(path, "\n".join(lines))
