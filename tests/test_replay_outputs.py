import json
import subprocess
import sys
from pathlib import Path


def test_replay_writes_required_artifacts_and_fields():
    run_id = "outputs_run"
    subprocess.run(
        [
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
        ],
        check=True,
    )
    base = Path("runs") / run_id
    required = [
        "manifest.json",
        "universe.jsonl",
        "backfill.jsonl",
        "signals.jsonl",
        "trades.jsonl",
        "positions.json",
        "replay_summary.json",
        "replay_summary.md",
    ]
    for name in required:
        assert (base / name).exists(), name

    signal = json.loads((base / "signals.jsonl").read_text().splitlines()[0])
    for key in ["run_id", "ts", "token_address", "pair_address", "decision", "x_status", "x_validation_score", "features"]:
        assert key in signal
