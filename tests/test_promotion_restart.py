from database import SQLiteRunStore
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
        "runtime_health_counters": {"runtime_current_state_stale_count": 2},
        "degraded_x_runtime": {"degraded_entries_attempted": 3},
    }
    write_session_state(path, saved)
    restored = restore_runtime_state(path, mode="shadow", config_hash="abc", resume=True)
    assert restored["open_positions"][0]["position_id"] == "p1"
    assert restored["counters"]["trades_today"] == 2
    assert restored["runtime_health_counters"]["runtime_current_state_stale_count"] == 2
    assert restored["resume_origin"] == "resume"


def test_sqlite_run_store_persists_checkpoint_payload(tmp_path):
    store = SQLiteRunStore(tmp_path / "run_store.sqlite3")
    store.record_run_started(
        run_id="ops_run",
        mode="expanded_paper",
        config_hash="cfg123",
        started_at="2026-03-21T10:00:00Z",
        session_path=str(tmp_path / "session.json"),
        manifest_path=str(tmp_path / "runtime_manifest.json"),
        payload={"seed": 42},
    )
    store.record_checkpoint(
        run_id="ops_run",
        checkpoint_ts="2026-03-21T10:05:00Z",
        session_path=str(tmp_path / "session.json"),
        summary_path=str(tmp_path / "daily_summary.json"),
        health_path=str(tmp_path / "runtime_health.json"),
        artifact_manifest_path=str(tmp_path / "artifact_manifest.json"),
        counters={"trades_today": 4},
        payload={"runtime_health": {"runtime_current_state_stale_count": 1}},
    )
    store.mark_run_completed(run_id="ops_run", ended_at="2026-03-21T11:00:00Z")

    run_payload = store.load_run("ops_run")
    latest_checkpoint = store.load_latest_checkpoint("ops_run")

    assert run_payload is not None
    assert latest_checkpoint is not None
    assert run_payload["latest_health_path"].endswith("runtime_health.json")
    assert latest_checkpoint["counters_json"]["trades_today"] == 4
    assert latest_checkpoint["payload_json"]["runtime_health"]["runtime_current_state_stale_count"] == 1
