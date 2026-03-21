from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from utils.io import read_json, write_json


def _config(tmp_path, *, mode: str = "expanded_paper") -> Path:
    payload = {
        "runtime": {"mode": mode, "chain": "solana", "loop_interval_sec": 0, "seed": 42},
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


def test_runtime_loop_opens_paper_position_from_real_signal(tmp_path):
    processed = tmp_path / "processed"
    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "real_entry_1",
                    "token_address": "SoReal111",
                    "pair_address": "Pair111",
                    "entry_decision": "SCALP",
                    "regime": "SCALP",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "regime_confidence": 0.9,
                    "entry_confidence": 0.88,
                    "recommended_position_pct": 0.4,
                    "continuation_confidence": 0.76,
                    "continuation_status": "confirmed",
                    "linkage_confidence": 0.8,
                    "linkage_risk_score": 0.12,
                    "bundle_wallet_clustering_score": 0.72,
                    "cluster_concentration_ratio": 0.24,
                    "x_validation_score": 82,
                    "entry_reason": "fixture_valid_real_entry",
                    "entry_snapshot": {"price_usd": 1.0},
                }
            ]
        },
    )
    config_path = _config(tmp_path, mode="expanded_paper")
    run_id = "real_signal_runtime"
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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    run_dir = tmp_path / "runs" / run_id
    summary = read_json(run_dir / "daily_summary.json", default={})
    positions = read_json(run_dir / "positions.json", default={})
    assert summary["runtime_signal_origin"] == "entry_candidates"
    assert summary["total_opened"] == 1
    assert positions["open_positions"][0]["token_address"] == "SoReal111"
    assert positions["open_positions"][0]["base_position_pct"] == 0.4
    assert positions["open_positions"][0]["effective_position_pct"] == 0.4
    assert positions["open_positions"][0]["sizing_multiplier"] == 1.0
    assert positions["open_positions"][0]["sizing_origin"] == "evidence_weighted"

    decision_row = json.loads((run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert decision_row["sizing_origin"] == "evidence_weighted"
    assert decision_row["sizing_reason_codes"]


def test_runtime_loop_respects_mode_guards_for_real_signal(tmp_path):
    processed = tmp_path / "processed"
    write_json(
        processed / "entry_candidates.json",
        {
            "tokens": [
                {
                    "signal_id": "blocked_trend",
                    "token_address": "SoBlocked111",
                    "pair_address": "Pair222",
                    "entry_decision": "TREND",
                    "regime": "TREND",
                    "x_status": "healthy",
                    "signal_ts": "2026-03-20T00:00:00+00:00",
                    "regime_confidence": 0.8,
                    "entry_confidence": 0.8,
                    "recommended_position_pct": 0.5,
                }
            ]
        },
    )
    config_path = _config(tmp_path, mode="constrained_paper")
    run_id = "real_signal_blocked"
    cmd = [
        sys.executable,
        "scripts/run_promotion_loop.py",
        "--config",
        str(config_path),
        "--mode",
        "constrained_paper",
        "--run-id",
        run_id,
        "--max-loops",
        "1",
        "--signals-dir",
        str(processed),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    decisions = (tmp_path / "runs" / run_id / "decisions.jsonl").read_text(encoding="utf-8")
    summary = read_json(tmp_path / "runs" / run_id / "daily_summary.json", default={})
    assert "regime_not_allowed" in decisions
    assert summary["total_opened"] == 0
    assert summary["total_rejected"] == 1


def test_runtime_loop_does_not_self_inject_captcha_cooldown(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    config_path = _config(tmp_path, mode="expanded_paper")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["runtime"]["seed"] = 31
    payload["x_protection"]["captcha_cooldown_trigger_count"] = 1
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    run_id = "no_synthetic_captcha"
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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    run_dir = tmp_path / "runs" / run_id
    event_log = (run_dir / "event_log.jsonl").read_text(encoding="utf-8")
    summary = read_json(run_dir / "daily_summary.json", default={})
    assert '"event": "cooldown_started"' not in event_log
    assert summary["x_cooldown_active"] is False
