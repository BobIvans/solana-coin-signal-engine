import subprocess
import sys
from pathlib import Path


def test_replay_smoke_end_to_end():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
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
            "smoke_replay_test",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert "[replay] done" in completed.stdout
