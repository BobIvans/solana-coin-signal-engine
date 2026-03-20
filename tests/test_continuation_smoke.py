from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_continuation_smoke_script_writes_expected_outputs(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_root))
    monkeypatch.setenv("RAW_DATA_DIR", str(data_root / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(data_root / "processed"))
    monkeypatch.setenv("SMOKE_DIR", str(data_root / "smoke"))

    completed = subprocess.run(
        [sys.executable, "scripts/continuation_smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(completed.stdout.strip())

    assert summary["continuation_status"] == "complete"
    assert summary["continuation_metric_origin"] == "mixed_evidence"
    assert (data_root / "smoke" / "continuation_enrichment.smoke.json").exists()
    assert (data_root / "smoke" / "continuation_status.json").exists()
    events_path = data_root / "smoke" / "continuation_events.jsonl"
    assert events_path.exists()
    events = events_path.read_text(encoding="utf-8").splitlines()
    assert any('continuation_enrichment_started' in line for line in events)
    assert any('continuation_completed' in line for line in events)
