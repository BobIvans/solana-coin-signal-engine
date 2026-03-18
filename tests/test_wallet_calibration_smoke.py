from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_wallet_calibration_smoke(tmp_path: Path):
    processed_dir = tmp_path / "processed"
    cmd = [
        sys.executable,
        "scripts/wallet_calibration_smoke.py",
        "--processed-dir",
        str(processed_dir),
        "--out-report",
        str(processed_dir / "wallet_calibration_report.json"),
        "--out-md",
        str(processed_dir / "wallet_calibration_summary.md"),
        "--out-recommendation",
        str(processed_dir / "wallet_rollout_recommendation.json"),
    ]
    completed = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    recommendation = json.loads(completed.stdout.strip())
    assert recommendation["safe_default_mode"] == "shadow"
    for name in [
        "wallet_calibration_report.json",
        "wallet_calibration_summary.md",
        "wallet_rollout_recommendation.json",
        "wallet_calibration_events.jsonl",
    ]:
        assert (processed_dir / name).exists(), name
