from __future__ import annotations

from pathlib import Path


def is_kill_switch_active(config: dict) -> bool:
    path = Path(config.get("safety", {}).get("kill_switch_file", "runs/runtime/kill_switch.flag"))
    return path.exists()


def trigger_kill_switch(state: dict, reason: str) -> dict:
    state["kill_switch_reason"] = reason
    return {"event": "kill_switch_triggered", "reason": reason}


def clear_kill_switch(config: dict) -> None:
    path = Path(config.get("safety", {}).get("kill_switch_file", "runs/runtime/kill_switch.flag"))
    if path.exists():
        path.unlink()
