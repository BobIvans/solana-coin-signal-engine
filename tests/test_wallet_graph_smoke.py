from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wallet_graph_smoke_script_runs_and_writes_outputs():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "wallet_graph_smoke.py")],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    payload = json.loads(completed.stdout.strip())

    assert payload["status"] == "ok"
    assert Path(payload["graph_path"]).exists()
    assert Path(payload["cluster_path"]).exists()
    assert Path(payload["event_path"]).exists()
