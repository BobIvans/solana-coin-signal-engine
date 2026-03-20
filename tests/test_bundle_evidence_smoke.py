import json
import subprocess
import sys
from pathlib import Path


def test_bundle_evidence_smoke_script(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = {
        **__import__("os").environ,
        "DATA_DIR": str(tmp_path),
        "SMOKE_DIR": str(tmp_path / "smoke"),
        "PROCESSED_DATA_DIR": str(tmp_path / "processed"),
        "RAW_DATA_DIR": str(tmp_path / "raw"),
    }
    run = subprocess.run(
        [sys.executable, "scripts/bundle_evidence_smoke.py"],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(run.stdout.strip().splitlines()[-1])
    assert payload["bundle_metric_origin"] == "real_evidence"
    assert (tmp_path / "smoke" / "bundle_evidence.smoke.json").exists()
    assert (tmp_path / "smoke" / "bundle_evidence_status.json").exists()
    assert (tmp_path / "smoke" / "bundle_evidence_events.jsonl").exists()
