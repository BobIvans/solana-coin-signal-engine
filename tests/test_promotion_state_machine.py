from src.promotion.state_machine import apply_transition, can_transition


def test_valid_transition():
    state = {"active_mode": "shadow"}
    assert can_transition("shadow", "constrained_paper", state, {})
    next_state, event = apply_transition("shadow", "constrained_paper", state, {})
    assert next_state["active_mode"] == "constrained_paper"
    assert event["event"] == "mode_entered"


def test_invalid_transition_mode_name():
    assert not can_transition("shadow", "invalid", {}, {})
