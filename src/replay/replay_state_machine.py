from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "idle": {"candidate_seen"},
    "candidate_seen": {"entry_blocked", "ignored", "position_opened", "unresolved"},
    "entry_blocked": set(),
    "ignored": set(),
    "position_opened": {"partial_exit", "full_exit", "unresolved"},
    "partial_exit": {"partial_exit", "full_exit", "unresolved"},
    "full_exit": set(),
    "unresolved": set(),
}


@dataclass
class ReplayStateMachine:
    token_address: str
    state: str = "idle"
    events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    partial_exit_count: int = 0

    def transition(self, next_state: str, **payload: Any) -> dict[str, Any]:
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if next_state not in allowed:
            raise ValueError(f"invalid replay transition {self.state!r} -> {next_state!r}")
        self.state = next_state
        event = {"state": next_state, "token_address": self.token_address, **payload}
        self.events.append(event)
        return event

    def candidate_seen(self, **payload: Any) -> dict[str, Any]:
        return self.transition("candidate_seen", **payload)

    def block_entry(self, **payload: Any) -> dict[str, Any]:
        return self.transition("entry_blocked", **payload)

    def ignore(self, **payload: Any) -> dict[str, Any]:
        return self.transition("ignored", **payload)

    def open_position(self, **payload: Any) -> dict[str, Any]:
        return self.transition("position_opened", **payload)

    def partial_exit(self, **payload: Any) -> dict[str, Any]:
        self.partial_exit_count += 1
        return self.transition("partial_exit", partial_exit_count=self.partial_exit_count, **payload)

    def full_exit(self, **payload: Any) -> dict[str, Any]:
        return self.transition("full_exit", **payload)

    def unresolved(self, **payload: Any) -> dict[str, Any]:
        warning = payload.get("warning")
        if warning:
            self.warnings.append(str(warning))
        return self.transition("unresolved", **payload)

    @property
    def resolution_status(self) -> str:
        if self.state == "full_exit":
            return "resolved"
        if self.state in {"entry_blocked", "ignored"}:
            return self.state
        if self.state == "unresolved":
            return "unresolved"
        return "incomplete"

    def snapshot(self) -> dict[str, Any]:
        return {
            "token_address": self.token_address,
            "state": self.state,
            "partial_exit_count": self.partial_exit_count,
            "resolution_status": self.resolution_status,
            "events": list(self.events),
            "warnings": list(dict.fromkeys(self.warnings)),
        }
