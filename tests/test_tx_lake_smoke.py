from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_tx_lake_smoke_script(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    smoke_dir = tmp_path / "smoke"
    lake_dir = tmp_path / "lake"
    completed = subprocess.run(
        [sys.executable, "scripts/tx_lake_smoke.py", "--smoke-dir", str(smoke_dir), "--lake-dir", str(lake_dir)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip())
    assert payload["record_count"] == 2
    assert (smoke_dir / "tx_lake_summary.json").exists()
    assert (smoke_dir / "tx_lake_status.json").exists()
    assert (smoke_dir / "tx_lake_events.jsonl").exists()
