import json
import subprocess
import sys
from pathlib import Path


def _run(run_id: str, wallet_weighting: str = "off"):
    cmd = [
        sys.executable,
        "scripts/replay_7d.py",
        "--artifact-dir",
        "tests/fixtures/historical_replay/full_win",
        "--config",
        "config/replay.default.yaml",
        "--days",
        "7",
        "--seed",
        "42",
        "--run-id",
        run_id,
        "--wallet-weighting",
        wallet_weighting,
        "--dry-run",
        "--start-ts",
        "2026-03-09T00:00:00Z",
        "--end-ts",
        "2026-03-16T00:00:00Z",
    ]
    subprocess.run(cmd, check=True)
    base = Path("runs") / run_id
    manifest = json.loads((base / "manifest.json").read_text())
    return (
        manifest["config_hash"],
        manifest["historical_input_hash"],
        manifest["wallet_weighting_requested_mode"],
        (base / "signals.jsonl").read_text(),
        (base / "trades.jsonl").read_text(),
        (base / "trade_feature_matrix.jsonl").read_text(),
        (base / "replay_summary.json").read_text(),
    )


def test_replay_is_deterministic_for_same_seed_and_window():
    out1 = _run("det_run", wallet_weighting="shadow")
    out2 = _run("det_run", wallet_weighting="shadow")
    assert out1 == out2
