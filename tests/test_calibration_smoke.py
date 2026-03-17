import json
import subprocess
import sys
from pathlib import Path

import yaml


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def test_calibration_smoke(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    replay_dir = runs_dir / "smoke_replay"
    replay_dir.mkdir(parents=True)

    (replay_dir / "manifest.json").write_text(json.dumps({"run_id": "smoke_replay"}), encoding="utf-8")
    (replay_dir / "replay_summary.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    signals = [{"timestamp_utc": f"2026-03-{day:02d}T00:00:00Z", "signal_id": f"s{day}"} for day in range(1, 8)]
    _write_jsonl(replay_dir / "signals.jsonl", signals)

    trades = []
    for day in range(1, 8):
        trades.append(
            {
                "entry_time_utc": f"2026-03-{day:02d}T01:00:00Z",
                "regime": "SCALP" if day % 2 else "TREND",
                "pnl_pct": 2.0 if day % 3 else -1.0,
                "final_score": 90,
                "buy_pressure": 0.8,
                "volume_velocity": 4.2,
                "rug_score": 0.1,
                "smart_wallet_hits": 3,
                "hold_seconds": 100,
                "liquidity_drop_pct": 10,
            }
        )
    _write_jsonl(replay_dir / "trades.jsonl", trades)

    config = {
        "input": {"replay_run_id": "smoke_replay", "runs_dir": str(runs_dir)},
        "seed": 42,
        "splits": {"mode": "by_day", "train_days": 5, "validation_days": 2, "require_non_overlapping": True},
        "selection": {
            "primary_metric": "validation_expectancy",
            "min_trades_total": 1,
            "min_trades_per_regime": 1,
            "require_baseline_outperformance": True,
        },
        "baseline": {
            "scalp_final_score_min": 82,
            "trend_final_score_min": 86,
            "buy_pressure_min": 0.75,
            "volume_velocity_min": 4.0,
            "rug_score_max_scalp": 0.30,
            "rug_score_max_trend": 0.20,
            "smart_wallet_hits_min": 2,
            "scalp_velocity_decay_ratio": 0.70,
            "scalp_buy_pressure_fail": 0.60,
            "scalp_max_hold_sec": 120,
            "trend_partial_1_pct": 35,
            "trend_partial_2_pct": 100,
            "trend_buy_pressure_fail": 0.50,
            "trend_liquidity_drop_fail_pct": 25,
        },
        "grid": {
            "scalp_final_score_min": [82],
            "trend_final_score_min": [86],
            "buy_pressure_min": [0.75, 0.78],
            "volume_velocity_min": [4.0],
            "rug_score_max_scalp": [0.30],
            "rug_score_max_trend": [0.20],
            "smart_wallet_hits_min": [2],
            "scalp_velocity_decay_ratio": [0.70],
            "scalp_buy_pressure_fail": [0.60],
            "scalp_max_hold_sec": [120],
            "trend_partial_1_pct": [35],
            "trend_partial_2_pct": [100],
            "trend_buy_pressure_fail": [0.50],
            "trend_liquidity_drop_fail_pct": [25],
        },
    }
    cfg_path = tmp_path / "calibration.yaml"
    cfg_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    cmd = [
        sys.executable,
        "scripts/calibrate_replay.py",
        "--config",
        str(cfg_path),
        "--replay-run-id",
        "smoke_replay",
        "--seed",
        "42",
        "--run-id",
        "calib_smoke",
        "--emit-recommended-config",
    ]
    completed = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout

    out_dir = runs_dir / "calib_smoke"
    for name in [
        "calibration_summary.json",
        "calibration_summary.md",
        "leaderboard.csv",
        "leaderboard.json",
        "recommended_config.yaml",
        "candidate_diffs.json",
    ]:
        assert (out_dir / name).exists(), name
