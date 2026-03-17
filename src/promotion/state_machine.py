from __future__ import annotations

from .types import VALID_MODES

_ALLOWED_TRANSITIONS = {
    "shadow": {"constrained_paper", "expanded_paper", "paused", "shadow"},
    "constrained_paper": {"shadow", "expanded_paper", "paused", "constrained_paper"},
    "expanded_paper": {"shadow", "constrained_paper", "paused", "expanded_paper"},
    "paused": {"shadow", "constrained_paper", "expanded_paper", "paused"},
}


def can_transition(current_mode: str, target_mode: str, state: dict, config: dict) -> bool:
    if current_mode not in VALID_MODES or target_mode not in VALID_MODES:
        return False
    return target_mode in _ALLOWED_TRANSITIONS.get(current_mode, set())


def enter_mode(mode: str, state: dict, config: dict) -> dict:
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    state["active_mode"] = mode
    return state


def apply_transition(current_mode: str, target_mode: str, state: dict, config: dict) -> tuple[dict, dict]:
    if not can_transition(current_mode, target_mode, state, config):
        raise ValueError(f"Invalid mode transition {current_mode} -> {target_mode}")
    enter_mode(target_mode, state, config)
    event = {
        "event": "mode_entered",
        "from": current_mode,
        "to": target_mode,
    }
    return state, event
