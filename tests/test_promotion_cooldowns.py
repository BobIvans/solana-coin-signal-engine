from datetime import datetime, timezone

from src.promotion.cooldowns import is_x_cooldown_active, normalize_x_error_type, register_x_error


CONFIG = {
    "x_protection": {
        "captcha_cooldown_trigger_count": 2,
        "captcha_cooldown_minutes": 30,
        "soft_ban_cooldown_minutes": 30,
        "timeout_cooldown_trigger_count": 5,
        "timeout_cooldown_minutes": 15,
    }
}



def test_two_captcha_triggers_cooldown():
    state = {}
    assert register_x_error("captcha", state, CONFIG) is None
    event = register_x_error("captcha", state, CONFIG)
    assert event and event["event"] == "cooldown_started"
    assert is_x_cooldown_active(state, datetime.now(timezone.utc))



def test_timeout_burst_triggers_cooldown():
    state = {}
    event = None
    for _ in range(5):
        event = register_x_error("timeout", state, CONFIG)
    assert event and event["type"] == "timeout"



def test_blocked_alias_is_normalized_to_soft_ban():
    state = {}
    assert normalize_x_error_type("blocked") == "soft_ban"
    event = register_x_error("blocked", state, CONFIG)
    assert event and event["type"] == "soft_ban"
    assert state["cooldowns"]["x"]["active_type"] == "soft_ban"
