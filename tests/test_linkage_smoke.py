from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_linkage_smoke_writes_expected_outputs(tmp_path: Path):
    smoke_dir = tmp_path / "linkage_smoke"
    subprocess.run(
        [sys.executable, "scripts/linkage_smoke.py", "--output-dir", str(smoke_dir)],
        check=True,
        cwd=ROOT,
    )

    score_path = smoke_dir / "linkage_score.smoke.json"
    status_path = smoke_dir / "linkage_status.json"
    events_path = smoke_dir / "linkage_events.jsonl"

    assert score_path.exists()
    assert status_path.exists()
    assert events_path.exists()

    score_payload = json.loads(score_path.read_text(encoding="utf-8"))
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert score_payload["linkage_risk_score"] is not None
    assert status_payload["linkage_status"] in {"ok", "partial"}
    assert len(events) == 3
    assert any(event["event"] == "linkage_score_computed" for event in events)
