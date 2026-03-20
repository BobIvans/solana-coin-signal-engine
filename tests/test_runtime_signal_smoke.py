from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from utils.io import read_json


def test_runtime_signal_smoke_script_writes_real_signal_outputs():
    cmd = [sys.executable, "scripts/runtime_signal_smoke.py"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    summary = read_json(Path("data/smoke/runtime_signal/runtime_signal_summary.json"), default={})
    assert summary["runtime_signal_origin"] == "entry_candidates"
    assert summary["runtime_signal_status"] in {"ok", "partial"}
    assert Path("data/smoke/runtime_signal/runtime_signal_decisions.jsonl").exists()
    assert Path("runs/runtime_signal_smoke/daily_summary.json").exists()

    stdout_payload = json.loads(result.stdout.strip())
    assert stdout_payload["signals_written"] == 3
