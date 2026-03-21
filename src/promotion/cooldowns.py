from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

X_ERROR_TYPE_ALIASES = {
    "blocked": "soft_ban",
    "soft-ban": "soft_ban",
    "soft_ban": "soft_ban",
    "429": "soft_ban",
    "rate_limited": "soft_ban",
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except ValueError:
        return None


def normalize_x_error_type(error_type: str | None) -> str:
    text = str(error_type or "").strip().lower()
    if not text:
        return ""
    return X_ERROR_TYPE_ALIASES.get(text, text)


def register_x_error(error_type: str, state: dict, config: dict) -> dict | None:
    now = datetime.now(timezone.utc)
    error_type = normalize_x_error_type(error_type)
    x_state = state.setdefault("cooldowns", {}).setdefault("x", {"captcha_streak": 0, "timeout_streak": 0})
    protection = config.get("x_protection", {})

    x_state["last_error_type"] = error_type
    x_state["last_error_at"] = _iso(now)

    if error_type == "captcha":
        x_state["captcha_streak"] = int(x_state.get("captcha_streak", 0)) + 1
        if x_state["captcha_streak"] >= int(protection.get("captcha_cooldown_trigger_count", 2)):
            until = now + timedelta(minutes=int(protection.get("captcha_cooldown_minutes", 30)))
            x_state["active_until"] = _iso(until)
            x_state["active_type"] = "captcha"
            x_state["captcha_streak"] = 0
            return {"event": "cooldown_started", "type": "captcha", "active_until": x_state["active_until"]}
    elif error_type == "soft_ban":
        until = now + timedelta(minutes=int(protection.get("soft_ban_cooldown_minutes", 30)))
        x_state["active_until"] = _iso(until)
        x_state["active_type"] = "soft_ban"
        x_state["captcha_streak"] = 0
        x_state["timeout_streak"] = 0
        return {"event": "cooldown_started", "type": "soft_ban", "active_until": x_state["active_until"]}
    elif error_type == "timeout":
        x_state["timeout_streak"] = int(x_state.get("timeout_streak", 0)) + 1
        if x_state["timeout_streak"] >= int(protection.get("timeout_cooldown_trigger_count", 5)):
            until = now + timedelta(minutes=int(protection.get("timeout_cooldown_minutes", 15)))
            x_state["active_until"] = _iso(until)
            x_state["active_type"] = "timeout"
            x_state["timeout_streak"] = 0
            return {"event": "cooldown_started", "type": "timeout", "active_until": x_state["active_until"]}
    return None


def is_x_cooldown_active(state: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    x_state = state.get("cooldowns", {}).get("x", {})
    active_until = x_state.get("active_until")
    if not active_until:
        return False
    parsed = _parse_iso(active_until)
    if parsed is None:
        return False
    return now < parsed

def get_x_cooldown_state(state: dict, now: datetime | None = None) -> dict[str, Any]:
    x_state = dict(state.get("cooldowns", {}).get("x", {}) or {})
    return {
        "active": is_x_cooldown_active(state, now),
        "active_until": x_state.get("active_until"),
        "active_type": x_state.get("active_type"),
        "last_error_type": x_state.get("last_error_type"),
        "last_error_at": x_state.get("last_error_at"),
    }


def resolve_degraded_x_policy(mode: str, config: dict) -> str:
    if mode == "constrained_paper":
        return config.get("degraded_x", {}).get("constrained_policy", "watchlist_only")
    if mode == "expanded_paper":
        return config.get("degraded_x", {}).get("expanded_policy", "reduced_size")
    return "watchlist_only"


def _degraded_x_limits(config: dict) -> dict[str, Any]:
    dx = config.get("degraded_x", {})
    return {
        "max_entries_per_hour": max(int(dx.get("max_entries_per_hour", 2) or 0), 0),
        "max_consecutive_signals_for_entry": max(int(dx.get("max_consecutive_signals_for_entry", 3) or 0), 0),
        "escalation_policy": str(dx.get("escalation_policy", "watchlist_only") or "watchlist_only"),
        "escalate_on_cooldown": bool(dx.get("escalate_on_cooldown", True)),
    }


def _degraded_x_state(state: dict) -> dict[str, Any]:
    runtime = state.setdefault(
        "degraded_x_runtime",
        {
            "consecutive_signals": 0,
            "last_signal_at": None,
            "first_degraded_at": None,
            "degraded_entry_opened_at": [],
            "degraded_entries_attempted": 0,
            "degraded_entries_opened": 0,
            "degraded_entries_blocked": 0,
        },
    )
    runtime.setdefault("degraded_entry_opened_at", [])
    return runtime


def observe_x_signal(signal: dict, state: dict, config: dict, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    runtime = _degraded_x_state(state)
    x_status = str(signal.get("x_status") or "").lower()
    runtime["last_signal_at"] = _iso(now)
    if x_status == "degraded":
        runtime["consecutive_signals"] = int(runtime.get("consecutive_signals", 0)) + 1
        runtime.setdefault("first_degraded_at", _iso(now))
    else:
        runtime["consecutive_signals"] = 0
        runtime["first_degraded_at"] = None
    return resolve_degraded_x_guard(state.get("active_mode"), state, config, now=now)


def register_degraded_x_entry_attempt(state: dict, *, blocked: bool = False, now: datetime | None = None) -> None:
    _ = now or datetime.now(timezone.utc)
    runtime = _degraded_x_state(state)
    runtime["degraded_entries_attempted"] = int(runtime.get("degraded_entries_attempted", 0)) + 1
    if blocked:
        runtime["degraded_entries_blocked"] = int(runtime.get("degraded_entries_blocked", 0)) + 1


def register_degraded_x_entry_opened(state: dict, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    runtime = _degraded_x_state(state)
    opened = [ts for ts in runtime.get("degraded_entry_opened_at", []) if _parse_iso(ts) is not None]
    opened.append(_iso(now))
    runtime["degraded_entry_opened_at"] = opened
    runtime["degraded_entries_opened"] = int(runtime.get("degraded_entries_opened", 0)) + 1


def resolve_degraded_x_guard(mode: str | None, state: dict, config: dict, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    mode = str(mode or state.get("active_mode") or "")
    limits = _degraded_x_limits(config)
    runtime = _degraded_x_state(state)
    window_start = now - timedelta(hours=1)

    recent_entries: list[str] = []
    for ts in runtime.get("degraded_entry_opened_at", []):
        parsed = _parse_iso(ts)
        if parsed is not None and parsed >= window_start:
            recent_entries.append(_iso(parsed))
    runtime["degraded_entry_opened_at"] = recent_entries

    base_policy = resolve_degraded_x_policy(mode, config)
    cooldown_active = is_x_cooldown_active(state, now)
    consecutive_signals = int(runtime.get("consecutive_signals", 0) or 0)
    budget_exhausted = limits["max_entries_per_hour"] > 0 and len(recent_entries) >= limits["max_entries_per_hour"]
    streak_exhausted = limits["max_consecutive_signals_for_entry"] > 0 and consecutive_signals > limits["max_consecutive_signals_for_entry"]
    escalated = bool((cooldown_active and limits["escalate_on_cooldown"]) or streak_exhausted)
    active_policy = limits["escalation_policy"] if escalated else base_policy

    reason_codes: list[str] = []
    if cooldown_active:
        reason_codes.append("x_cooldown_policy_block")
    if budget_exhausted:
        reason_codes.append("degraded_x_budget_exhausted")
    if escalated and active_policy == "watchlist_only":
        reason_codes.append("degraded_x_escalated_to_watchlist_only")
    elif escalated and active_policy == "pause_new_entries":
        reason_codes.append("degraded_x_escalated_to_pause_new_entries")

    return {
        "base_policy": base_policy,
        "active_policy": active_policy,
        "cooldown_active": cooldown_active,
        "budget_exhausted": budget_exhausted,
        "escalated": escalated,
        "consecutive_signals": consecutive_signals,
        "degraded_entries_last_hour": len(recent_entries),
        "reason_codes": reason_codes,
    }
