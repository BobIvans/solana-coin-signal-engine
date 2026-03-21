from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from utils.io import read_json, write_json
import scripts.run_promotion_loop as loop


def _config(tmp_path) -> Path:
    payload = {
        "runtime": {"mode": "expanded_paper", "chain": "solana", "loop_interval_sec": 0, "seed": 42},
        "modes": {
            "shadow": {"open_positions": False, "simulate_entries": True, "simulate_exits": True, "allow_regimes": ["SCALP", "TREND"]},
            "constrained_paper": {"open_positions": True, "max_open_positions": 1, "max_trades_per_day": 10, "position_size_scale": 0.5, "allow_regimes": ["SCALP"], "degraded_x_policy": "watchlist_only"},
            "expanded_paper": {"open_positions": True, "max_open_positions": 2, "max_trades_per_day": 20, "position_size_scale": 1.0, "allow_regimes": ["SCALP", "TREND"], "degraded_x_policy": "reduced_size"},
            "paused": {"open_positions": False, "simulate_entries": False, "simulate_exits": False, "allow_regimes": ["SCALP", "TREND"]},
        },
        "safety": {"kill_switch_file": str(tmp_path / "kill.flag"), "max_daily_loss_pct": 8.0, "max_consecutive_losses": 4},
        "x_protection": {"captcha_cooldown_trigger_count": 2, "captcha_cooldown_minutes": 30, "soft_ban_cooldown_minutes": 30, "timeout_cooldown_trigger_count": 5, "timeout_cooldown_minutes": 15},
        "degraded_x": {
            "baseline_score": 45,
            "allow_shadow": True,
            "allow_constrained_paper": True,
            "allow_expanded_paper": True,
            "constrained_policy": "watchlist_only",
            "expanded_policy": "reduced_size",
            "max_entries_per_hour": 2,
            "max_consecutive_signals_for_entry": 2,
            "escalation_policy": "watchlist_only",
        },
        "state": {"runs_dir": str(tmp_path / "runs"), "state_dir": str(tmp_path / "runtime_state"), "write_session_state": True, "write_event_log": True, "write_daily_summary": True},
    }
    path = tmp_path / "promotion.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(config_path: Path, processed: Path, run_id: str, *, resume: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/run_promotion_loop.py",
        "--config",
        str(config_path),
        "--mode",
        "expanded_paper",
        "--run-id",
        run_id,
        "--max-loops",
        "1",
        "--signals-dir",
        str(processed),
    ]
    if resume:
        cmd.append("--resume")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_open_position_uses_cached_fallback_refresh_when_missing_from_fresh_batch(tmp_path):
    processed = tmp_path / "processed"
    config_path = _config(tmp_path)
    run_id = "runtime_cached_fallback"

    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "open_1",
                    "token_address": "SoCache111",
                    "pair_address": "PairCache111",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "recommended_position_pct": 0.4,
                    "price_usd_now": 1.17,
                    "liquidity_usd_now": 25000,
                    "buy_pressure_now": 0.81,
                    "volume_velocity_now": 4.1,
                    "x_validation_score_now": 81,
                    "entry_snapshot": {"price_usd": 1.17, "liquidity_usd": 25000, "buy_pressure": 0.81, "volume_velocity": 4.1, "x_validation_score": 81, "x_status": "healthy"},
                }
            ]
        },
    )
    first = _run(config_path, processed, run_id)
    assert first.returncode == 0, first.stderr

    write_json(processed / "entry_candidates.json", {"tokens": []})
    second = _run(config_path, processed, run_id, resume=True)
    assert second.returncode == 0, second.stderr

    run_dir = tmp_path / "runs" / run_id
    summary = read_json(run_dir / "daily_summary.json", default={})
    positions = read_json(run_dir / "positions.json", default={})

    assert summary["runtime_current_state_fallback_count"] >= 1
    assert summary["runtime_current_state_stale_count"] == 0
    assert positions["open_positions"][0]["last_mark_price_usd"] == 1.17


def test_open_position_marks_stale_entry_snapshot_when_no_refresh_cache_exists(tmp_path):
    processed = tmp_path / "processed"
    config_path = _config(tmp_path)
    run_id = "runtime_honest_stale"

    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "open_2",
                    "token_address": "SoStale111",
                    "pair_address": "PairStale111",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "recommended_position_pct": 0.4,
                    "entry_snapshot": {"price_usd": 1.05, "liquidity_usd": 20000, "buy_pressure": 0.75, "volume_velocity": 3.0, "x_validation_score": 79, "x_status": "healthy"},
                }
            ]
        },
    )
    first = _run(config_path, processed, run_id)
    assert first.returncode == 0, first.stderr

    session_path = tmp_path / "runs" / run_id / "session_state.json"
    session = read_json(session_path, default={})
    session.pop("runtime_market_state_cache", None)
    write_json(session_path, session)
    write_json(processed / "entry_candidates.json", {"tokens": []})

    second = _run(config_path, processed, run_id, resume=True)
    assert second.returncode == 0, second.stderr

    summary = read_json(tmp_path / "runs" / run_id / "daily_summary.json", default={})
    assert summary["runtime_current_state_stale_count"] >= 1


def test_monitoring_refresh_happens_before_entry_processing_in_event_log(tmp_path):
    processed = tmp_path / "processed"
    config_path = _config(tmp_path)
    run_id = "runtime_monitoring_first"

    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "open_existing",
                    "token_address": "SoOrder111",
                    "pair_address": "PairOrder111",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "recommended_position_pct": 0.4,
                    "entry_snapshot": {"price_usd": 1.0, "buy_pressure": 0.8, "volume_velocity": 4.0, "x_validation_score": 80, "x_status": "healthy"},
                }
            ]
        },
    )
    first = _run(config_path, processed, run_id)
    assert first.returncode == 0, first.stderr

    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "new_entry",
                    "token_address": "SoOrder222",
                    "pair_address": "PairOrder222",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:01:00+00:00",
                    "recommended_position_pct": 0.4,
                    "entry_snapshot": {"price_usd": 1.2, "buy_pressure": 0.85, "volume_velocity": 4.2, "x_validation_score": 83, "x_status": "healthy"},
                }
            ]
        },
    )
    second = _run(config_path, processed, run_id, resume=True)
    assert second.returncode == 0, second.stderr

    events = [json.loads(line) for line in (tmp_path / "runs" / run_id / "event_log.jsonl").read_text(encoding="utf-8").splitlines()]
    refresh_index = next(i for i, row in enumerate(events) if row.get("event") == "runtime_current_state_refresh_completed")
    sizing_index = next(i for i, row in enumerate(events) if row.get("event") == "evidence_weighted_sizing_completed")
    assert refresh_index < sizing_index



def test_runtime_market_state_cache_prunes_stale_unpinned_entries(tmp_path):
    state = {
        "positions": [],
        "runtime_market_state_cache": {
            "fresh_live": {"token_address": "fresh_live", "cached_at": "2026-03-21T00:00:00+00:00"},
            "stale_drop": {"token_address": "stale_drop", "cached_at": "2020-01-01T00:00:00+00:00"},
        },
    }
    summary = loop._prune_runtime_market_state_cache(state, [{"token_address": "fresh_live"}], max_cache_age_sec=60, max_cache_entries=10)

    assert "stale_drop" not in state["runtime_market_state_cache"]
    assert "fresh_live" in state["runtime_market_state_cache"]
    assert summary["runtime_market_cache_pruned_count"] == 1



def test_runtime_market_state_cache_keeps_open_position_entries_pinned(tmp_path):
    state = {
        "positions": [{"token_address": "pinned_tok", "is_open": True}],
        "runtime_market_state_cache": {
            "pinned_tok": {"token_address": "pinned_tok", "cached_at": "2020-01-01T00:00:00+00:00"},
            "stale_drop": {"token_address": "stale_drop", "cached_at": "2020-01-01T00:00:00+00:00"},
        },
    }
    summary = loop._prune_runtime_market_state_cache(state, [], max_cache_age_sec=60, max_cache_entries=1)

    assert "pinned_tok" in state["runtime_market_state_cache"]
    assert "stale_drop" not in state["runtime_market_state_cache"]
    assert summary["runtime_market_cache_pinned_count"] == 1
