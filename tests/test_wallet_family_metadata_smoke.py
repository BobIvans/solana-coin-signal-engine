from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wallet_family_metadata_smoke_script_writes_outputs(tmp_path: Path):
    out_dir = tmp_path / "smoke"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/wallet_family_metadata_smoke.py",
            "--out-dir",
            str(out_dir),
            "--generated-at",
            "2024-01-02T00:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    compact = json.loads(completed.stdout.strip().splitlines()[-1])
    metadata_path = out_dir / "wallet_family_metadata.smoke.json"
    summary_path = out_dir / "wallet_family_summary.json"

    assert metadata_path.exists()
    assert summary_path.exists()
    assert compact["family_count"] >= 3
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert metadata["summary"]["family_count"] == compact["family_count"]
    assert summary["summary"]["wallet_count"] == metadata["summary"]["wallet_count"]
    assert metadata["family_assignments"]
