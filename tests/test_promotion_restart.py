from src.promotion.session import restore_runtime_state, write_session_state


def test_resume_restores_state(tmp_path):
    path = tmp_path / "session_state.json"
    saved = {
        "active_mode": "constrained_paper",
        "open_positions": [{"position_id": "p1"}],
        "counters": {"trades_today": 2, "pnl_pct_today": 1.2},
        "cooldowns": {},
        "consecutive_losses": 1,
        "current_day": "2026-03-16",
        "config_hash": "abc",
    }
    write_session_state(path, saved)
    restored = restore_runtime_state(path, mode="shadow", config_hash="abc", resume=True)
    assert restored["open_positions"][0]["position_id"] == "p1"
    assert restored["counters"]["trades_today"] == 2
