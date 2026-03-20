from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offline_feature_importance_smoke_script_writes_outputs():
    result = subprocess.run(
        [sys.executable, "scripts/offline_feature_importance_smoke.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    marker = result.stdout.rfind('{\n  "analysis_only"')
    assert marker >= 0, result.stdout
    payload = json.loads(result.stdout[marker:])
    assert payload["analysis_only"] is True
    assert payload["targets"]["profitable_trade_flag"]["top_feature"]
    assert (ROOT / "data" / "smoke" / "offline_feature_importance.json").exists()
    assert (ROOT / "data" / "smoke" / "offline_feature_importance_summary.md").exists()
