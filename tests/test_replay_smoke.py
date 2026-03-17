import subprocess
import sys


def test_replay_smoke_end_to_end():
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
            "smoke_replay",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "[replay] done" in completed.stdout
