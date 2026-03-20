from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unified_score_smoke_script_runs_real_smoke_path(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_root))
    monkeypatch.setenv("RAW_DATA_DIR", str(data_root / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(data_root / "processed"))
    monkeypatch.setenv("SMOKE_DIR", str(data_root / "smoke"))

    completed = subprocess.run(
        [sys.executable, "scripts/unified_score_smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(completed.stdout.strip())

    assert summary["off"]["final_score"] == summary["off"]["final_score_pre_wallet"]
    assert summary["off"]["wallet_score_component_applied"] == 0.0
    assert summary["shadow"]["final_score"] == summary["shadow"]["final_score_pre_wallet"]
    assert summary["shadow"]["wallet_score_component_raw"] > 0.0
    assert summary["shadow"]["wallet_score_component_applied"] == 0.0
    assert summary["on"]["final_score"] > summary["on"]["final_score_pre_wallet"]
    assert summary["on"]["wallet_score_component_applied"] > 0.0
    assert summary["batch_event_count"] == 1
    assert summary["batch_event_wallet_mode"] == "shadow"
    assert Path(summary["summary_path"]).exists()
