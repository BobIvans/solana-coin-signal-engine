from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import SessionState


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not str(key).startswith("__")}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _normalize_runtime_state(state: dict | None) -> dict | None:
    if not isinstance(state, dict):
        return state
    positions = state.get("positions")
    open_positions = state.get("open_positions")
    if not isinstance(positions, list):
        positions = []
    if not positions and isinstance(open_positions, list):
        positions = [
            {
                **dict(position),
                "is_open": bool(position.get("is_open", True)),
            }
            for position in open_positions
            if isinstance(position, dict)
        ]
    state["positions"] = positions
    state["open_positions"] = [dict(position) for position in positions if position.get("is_open", True)]
    state.setdefault("portfolio", {})
    state.setdefault("counters", {"trades_today": 0, "pnl_pct_today": 0.0})
    state.setdefault("cooldowns", {})
    state.setdefault("consecutive_losses", 0)
    state.setdefault("next_position_seq", 1)
    state.setdefault("next_trade_seq", 1)
    return state


def load_session_state(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return _normalize_runtime_state(json.loads(p.read_text(encoding="utf-8")))


def write_session_state(path: str | Path, state: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_safe(_normalize_runtime_state(dict(state)) or {})
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def restore_runtime_state(session_path: str | Path, mode: str, config_hash: str, resume: bool = False) -> dict:
    if resume:
        restored = load_session_state(session_path)
        if restored:
            return restored
    return SessionState(active_mode=mode, config_hash=config_hash).as_dict()
