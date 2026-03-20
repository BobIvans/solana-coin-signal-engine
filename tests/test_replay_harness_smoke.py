from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_historical_replay_smoke_script_runs_and_writes_outputs():
    completed = subprocess.run(
        [sys.executable, "scripts/historical_replay_smoke.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["historical_rows_used"] == 1
    assert (ROOT / "data" / "smoke" / "historical_replay_summary.json").exists()
    assert (ROOT / "data" / "smoke" / "historical_trade_feature_matrix.jsonl").exists()
