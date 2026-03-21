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


SESSION_SCHEMA_VERSION = "promotion_session.v2"


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
    runtime_metrics: dict[str, Any] = field(default_factory=dict)
    runtime_health_counters: dict[str, Any] = field(default_factory=dict)
    artifact_manifest: dict[str, Any] = field(default_factory=dict)
    last_checkpoint_ts: str = field(default_factory=utc_now_iso)
    resume_origin: str = "fresh"
    session_schema_version: str = SESSION_SCHEMA_VERSION

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
            "runtime_metrics": self.runtime_metrics,
            "runtime_health_counters": self.runtime_health_counters,
            "artifact_manifest": self.artifact_manifest,
            "last_checkpoint_ts": self.last_checkpoint_ts,
            "resume_origin": self.resume_origin,
            "session_schema_version": self.session_schema_version,
        }


VALID_MODES = {m.value for m in RuntimeMode}
