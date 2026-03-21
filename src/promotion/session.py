from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import SESSION_SCHEMA_VERSION, SessionState, utc_now_iso


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
    state.setdefault("runtime_metrics", {})
    state.setdefault("runtime_health_counters", {})
    state.setdefault("artifact_manifest", {})
    state.setdefault("resume_origin", "fresh")
    state.setdefault("session_schema_version", SESSION_SCHEMA_VERSION)
    state.setdefault("last_checkpoint_ts", utc_now_iso())
    return state


def load_session_state(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return _normalize_runtime_state(json.loads(p.read_text(encoding="utf-8")))


def write_session_state(path: str | Path, state: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_runtime_state(dict(state)) or {}
    normalized["session_schema_version"] = normalized.get("session_schema_version") or SESSION_SCHEMA_VERSION
    normalized["last_checkpoint_ts"] = normalized.get("last_checkpoint_ts") or utc_now_iso()
    if not normalized.get("runtime_health_counters") and normalized.get("runtime_metrics"):
        normalized["runtime_health_counters"] = dict(normalized.get("runtime_metrics") or {})
    payload = _json_safe(normalized)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def restore_runtime_state(session_path: str | Path, mode: str, config_hash: str, resume: bool = False) -> dict:
    if resume:
        restored = load_session_state(session_path)
        if restored:
            restored["resume_origin"] = "resume"
            restored.setdefault("config_hash", config_hash)
            return restored
    fresh = SessionState(active_mode=mode, config_hash=config_hash).as_dict()
    fresh["resume_origin"] = "fresh"
    fresh["last_checkpoint_ts"] = utc_now_iso()
    return fresh
