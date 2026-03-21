from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RuntimeMode(str, Enum):
    SHADOW = "shadow"
    CONSTRAINED_PAPER = "constrained_paper"
    EXPANDED_PAPER = "expanded_paper"
    PAUSED = "paused"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionState:
    active_mode: str
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    counters: dict[str, Any] = field(default_factory=lambda: {"trades_today": 0, "pnl_pct_today": 0.0, "realized_pnl_sol_today": 0.0, "starting_capital_sol": 0.0})
    cooldowns: dict[str, Any] = field(default_factory=dict)
    consecutive_losses: int = 0
    current_day: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    config_hash: str = ""
    force_watchlist_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_mode": self.active_mode,
            "open_positions": self.open_positions,
            "counters": self.counters,
            "cooldowns": self.cooldowns,
            "consecutive_losses": self.consecutive_losses,
            "current_day": self.current_day,
            "config_hash": self.config_hash,
            "force_watchlist_only": self.force_watchlist_only,
        }


VALID_MODES = {m.value for m in RuntimeMode}
