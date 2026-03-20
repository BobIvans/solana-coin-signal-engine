import json
import subprocess
import sys
from pathlib import Path


def test_analyzer_slices_smoke_script(tmp_path):
    out_dir = tmp_path / "smoke"
    result = subprocess.run(
        [sys.executable, "scripts/analyzer_slices_smoke.py", "--base-dir", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert Path(payload["analyzer_slices_path"]).exists()
    assert Path(payload["summary_markdown_path"]).exists()

    analyzer_slices = json.loads(Path(payload["analyzer_slices_path"]).read_text(encoding="utf-8"))
    assert analyzer_slices["metadata"]["contract_version"] == "analyzer_slices.v1"
    assert analyzer_slices["slice_groups"]["regime"]["trend_promoted_but_failed_fast"]["sample_size"] >= 1
    assert "evidence_quality" in analyzer_slices["slice_groups"]
