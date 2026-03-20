from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_docs_sync_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    smoke_dir = repo_root / "data" / "smoke"
    report_path = smoke_dir / "contract_parity_report.json"
    summary_path = smoke_dir / "contract_parity_summary.md"

    if report_path.exists():
        report_path.unlink()
    if summary_path.exists():
        summary_path.unlink()

    completed = subprocess.run(
        [sys.executable, "scripts/contract_parity_smoke.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout

    compact = json.loads(completed.stdout.strip())
    assert compact["overall_status"] == "ok"
    assert report_path.exists()
    assert summary_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["docs_sync"]["status"] == "ok"
    assert any(event["event"] == "docs_sync_checked" for event in report["events"])
    assert "Contract parity smoke summary" in summary_path.read_text(encoding="utf-8")
