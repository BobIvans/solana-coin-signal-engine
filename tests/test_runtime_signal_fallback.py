from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from utils.io import read_json, write_json


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
        "degraded_x": {"baseline_score": 45, "allow_shadow": True, "allow_constrained_paper": True, "allow_expanded_paper": True, "constrained_policy": "watchlist_only", "expanded_policy": "reduced_size"},
        "state": {"runs_dir": str(tmp_path / "runs"), "state_dir": str(tmp_path / "runtime_state"), "write_session_state": True, "write_event_log": True, "write_daily_summary": True},
    }
    path = tmp_path / "promotion.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_runtime_loop_degrades_safely_when_artifacts_missing(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    config_path = _config(tmp_path)
    run_id = "runtime_missing_artifacts"
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
        "--dry-run",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    summary = read_json(tmp_path / "runs" / run_id / "daily_summary.json", default={})
    assert summary["runtime_signal_status"] == "missing"
    assert summary["total_opened"] == 0


def test_runtime_loop_skips_malformed_rows_without_crashing(tmp_path):
    processed = tmp_path / "processed"
    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "bad_row",
                    "token_address": "",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "regime_confidence": 0.9,
                    "recommended_position_pct": 0.4,
                },
                {
                    "signal_id": "good_row",
                    "token_address": "SoGood111",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "degraded",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "regime_confidence": 0.9,
                    "entry_confidence": 0.8,
                    "recommended_position_pct": 0.4,
                }
            ]
        },
    )
    config_path = _config(tmp_path)
    run_id = "runtime_malformed_rows"
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
        "--dry-run",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    event_log = (tmp_path / "runs" / run_id / "event_log.jsonl").read_text(encoding="utf-8")
    summary = read_json(tmp_path / "runs" / run_id / "daily_summary.json", default={})
    assert "runtime_signal_invalid" in event_log
    assert "runtime_signal_partial" not in event_log or "SoGood111" in event_log
    assert summary["total_invalid"] == 1
