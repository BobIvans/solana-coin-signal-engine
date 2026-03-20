from __future__ import annotations

import pytest

from src.replay.replay_state_machine import ReplayStateMachine


def test_state_machine_tracks_resolved_lifecycle():
    machine = ReplayStateMachine(token_address="tok_test")
    machine.candidate_seen()
    machine.open_position(entry_price=1.0)
    machine.partial_exit(exit_reason="trend_partial_take_profit_1")
    machine.full_exit(exit_reason="cluster_dump_detected")

    snapshot = machine.snapshot()
    assert snapshot["state"] == "full_exit"
    assert snapshot["resolution_status"] == "resolved"
    assert snapshot["partial_exit_count"] == 1


def test_state_machine_rejects_invalid_transition():
    machine = ReplayStateMachine(token_address="tok_invalid")
    with pytest.raises(ValueError):
        machine.full_exit(exit_reason="nope")
