import json
import subprocess
import sys
from pathlib import Path


def _run(run_id: str):
    cmd = [
        sys.executable,
        "scripts/replay_7d.py",
        "--config",
        "config/replay.default.yaml",
        "--days",
        "7",
        "--seed",
        "42",
        "--run-id",
        run_id,
        "--dry-run",
        "--start-ts",
        "2026-03-09T00:00:00Z",
        "--end-ts",
        "2026-03-16T00:00:00Z",
    ]
    subprocess.run(cmd, check=True)
    base = Path("runs") / run_id
    return (
        json.loads((base / "manifest.json").read_text())["config_hash"],
        (base / "signals.jsonl").read_text(),
        (base / "trades.jsonl").read_text(),
        (base / "trade_feature_matrix.jsonl").read_text(),
        (base / "replay_summary.json").read_text(),
    )


def test_replay_is_deterministic_for_same_seed_and_window():
    out1 = _run("det_run")
    out2 = _run("det_run")
    assert out1 == out2
