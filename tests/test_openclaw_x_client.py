from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import collectors.openclaw_x_client as client
import collectors.x_query_builder as x_query_builder



def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        PROCESSED_DATA_DIR=tmp_path,
        OPENCLAW_X_QUERY_MAX=4,
        OPENCLAW_X_TOKEN_MAX_CONCURRENCY=3,
        OPENCLAW_X_CACHE_TTL_SEC=300,
        OPENCLAW_X_PAGE_TIMEOUT_MS=100,
        OPENCLAW_X_MAX_POSTS_PER_QUERY=5,
        OPENCLAW_BROWSER_PROFILE="profile",
        OPENCLAW_BROWSER_TARGET="target",
        LOCAL_OPENCLAW_ONLY=True,
    )



def test_fetch_x_snapshots_runs_queries_concurrently(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(client, "_GLOBAL_SEMAPHORE", threading.Semaphore(10))
    monkeypatch.setattr(x_query_builder, "build_queries", lambda token: [
        {"query": "q1", "query_type": "symbol", "normalized_query": "q1"},
        {"query": "q2", "query_type": "contract", "normalized_query": "q2"},
        {"query": "q3", "query_type": "name", "normalized_query": "q3"},
    ])

    counters = {"active": 0, "max_active": 0}
    lock = threading.Lock()

    def fake_fetch_single_query(query_obj):
        with lock:
            counters["active"] += 1
            counters["max_active"] = max(counters["max_active"], counters["active"])
        time.sleep(0.05)
        with lock:
            counters["active"] -= 1
        return {
            "token_address": "tok",
            "query": query_obj["query"],
            "query_type": query_obj["query_type"],
            "x_status": "ok",
            "posts_visible": 1,
            "authors_visible": ["author"],
            "cards": [],
            "error_code": None,
            "error_detail": None,
            "cache_hit": False,
        }

    monkeypatch.setattr(client, "fetch_single_query", fake_fetch_single_query)
    snapshots = client.fetch_x_snapshots({"token_address": "tok"})

    assert len(snapshots) == 3
    assert counters["max_active"] >= 2



def test_fetch_single_query_uses_status_specific_cache_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(client, "cache_get", lambda cache_name, key: None)
    captured = {}
    monkeypatch.setattr(client, "cache_set", lambda cache_name, key, value, ttl_sec=None: captured.update({"ttl_sec": ttl_sec, "value": value}))
    monkeypatch.setattr(client.shutil, "which", lambda _: "/usr/bin/openclaw")
    monkeypatch.setattr(client.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="429 blocked", stdout=""))

    snapshot = client.fetch_single_query({
        "token_address": "tok",
        "query": "tok",
        "query_type": "symbol",
        "normalized_query": "tok",
        "events_path": str(tmp_path / "events.jsonl"),
    })

    assert snapshot["error_code"] == "soft_ban"
    assert captured["ttl_sec"] == 90



def test_fetch_x_snapshots_registers_soft_ban_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(x_query_builder, "build_queries", lambda token: [
        {"query": "q1", "query_type": "symbol", "normalized_query": "q1"},
        {"query": "q2", "query_type": "symbol", "normalized_query": "q2"},
    ])
    results = iter([
        {"token_address": "tok", "query": "q1", "query_type": "symbol", "x_status": "ok", "posts_visible": 1, "authors_visible": [], "cards": [], "error_code": None, "error_detail": None, "cache_hit": False},
        {"token_address": "tok", "query": "q2", "query_type": "symbol", "x_status": "soft_ban", "posts_visible": 0, "authors_visible": [], "cards": [], "error_code": "blocked", "error_detail": "429", "cache_hit": False},
    ])
    monkeypatch.setattr(client, "fetch_single_query", lambda query_obj: next(results))

    state = {}
    config = {"x_protection": {"captcha_cooldown_trigger_count": 2, "captcha_cooldown_minutes": 30, "soft_ban_cooldown_minutes": 30, "timeout_cooldown_trigger_count": 5, "timeout_cooldown_minutes": 15}}
    snapshots = client.fetch_x_snapshots({"token_address": "tok"}, state=state, config=config)

    assert len(snapshots) == 2
    assert state["cooldowns"]["x"]["active_type"] == "soft_ban"
    assert any(snapshot.get("cooldown_event", {}).get("type") == "soft_ban" for snapshot in snapshots)



def test_fetch_x_snapshots_short_circuits_when_cooldown_active(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(x_query_builder, "build_queries", lambda token: [
        {"query": "q1", "query_type": "symbol", "normalized_query": "q1"},
        {"query": "q2", "query_type": "contract", "normalized_query": "q2"},
    ])

    called = {"workers": 0, "fetches": 0}

    class FailExecutor:
        def __init__(self, *args, **kwargs):
            called["workers"] += 1
            raise AssertionError("thread pool should not start during cooldown")

    def fail_fetch_single_query(query_obj):
        called["fetches"] += 1
        raise AssertionError("fetch_single_query should not be called during cooldown")

    monkeypatch.setattr(client, "ThreadPoolExecutor", FailExecutor)
    monkeypatch.setattr(client, "fetch_single_query", fail_fetch_single_query)

    state = {"cooldowns": {"x": {"active_until": "2999-01-01T00:00:00+00:00", "active_type": "soft_ban"}}}
    config = {"x_protection": {"captcha_cooldown_trigger_count": 2, "captcha_cooldown_minutes": 30, "soft_ban_cooldown_minutes": 30, "timeout_cooldown_trigger_count": 5, "timeout_cooldown_minutes": 15}}
    snapshots = client.fetch_x_snapshots({"token_address": "tok"}, state=state, config=config)

    assert len(snapshots) == 2
    assert called["workers"] == 0
    assert called["fetches"] == 0
    assert state["runtime_metrics"]["x_cooldown_skip_count"] == 2



def test_fetch_x_snapshots_returns_degraded_cooldown_snapshots_without_worker_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(x_query_builder, "build_queries", lambda token: [
        {"query": "q1", "query_type": "symbol", "normalized_query": "q1"},
        {"query": "q2", "query_type": "contract", "normalized_query": "q2"},
        {"query": "q3", "query_type": "name", "normalized_query": "q3"},
    ])
    monkeypatch.setattr(client, "fetch_single_query", lambda query_obj: (_ for _ in ()).throw(AssertionError("unexpected worker call")))

    state = {"cooldowns": {"x": {"active_until": "2999-01-01T00:00:00+00:00", "active_type": "timeout"}}}
    config = {"x_protection": {"captcha_cooldown_trigger_count": 2, "captcha_cooldown_minutes": 30, "soft_ban_cooldown_minutes": 30, "timeout_cooldown_trigger_count": 5, "timeout_cooldown_minutes": 15}}
    snapshots = client.fetch_x_snapshots({"token_address": "tok"}, state=state, config=config)

    assert len(snapshots) == 3
    for snapshot in snapshots:
        assert snapshot["x_status"] == "degraded"
        assert snapshot["error_code"] == "cooldown_active"
        assert snapshot["error_detail"] == "x_cooldown_active"
        assert snapshot["posts_visible"] == 0
        assert snapshot["cards"] == []
        assert snapshot["cooldown_active"] is True
        assert snapshot["cooldown_type"] == "timeout"

    event_log = (tmp_path / "x_validation_events.jsonl").read_text(encoding="utf-8")
    assert 'x_query_skipped_cooldown' in event_log
    assert 'x_snapshot_batch_skipped_cooldown' in event_log
