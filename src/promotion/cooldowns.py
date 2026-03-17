from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def register_x_error(error_type: str, state: dict, config: dict) -> dict | None:
    now = datetime.now(timezone.utc)
    x_state = state.setdefault("cooldowns", {}).setdefault("x", {"captcha_streak": 0, "timeout_streak": 0})
    protection = config.get("x_protection", {})

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
    return now < datetime.fromisoformat(active_until)


def resolve_degraded_x_policy(mode: str, config: dict) -> str:
    if mode == "constrained_paper":
        return config.get("degraded_x", {}).get("constrained_policy", "watchlist_only")
    if mode == "expanded_paper":
        return config.get("degraded_x", {}).get("expanded_policy", "reduced_size")
    return "watchlist_only"
