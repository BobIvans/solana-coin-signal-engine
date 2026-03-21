from __future__ import annotations

import json
from pathlib import Path


def write_daily_summary_json(path: str | Path, summary: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def write_daily_summary_md(path: str | Path, summary: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Daily Summary ({summary.get('run_id', '-')})",
        "",
        f"- Mode: `{summary.get('mode')}`",
        f"- Trades today: `{summary.get('trades_today')}`",
        f"- Open positions: `{summary.get('open_positions')}`",
        f"- PnL % today: `{summary.get('pnl_pct_today')}`",
        f"- Realized PnL today (SOL): `{summary.get('realized_pnl_sol_today')}`",
        f"- Daily loss %: `{summary.get('daily_loss_pct')}`",
        f"- Consecutive losses: `{summary.get('consecutive_losses')}`",
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
