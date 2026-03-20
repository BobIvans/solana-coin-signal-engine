from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_false_positive_smoke_script(tmp_path: Path):
    out_json = tmp_path / "false_positive_summary.json"
    out_md = tmp_path / "false_positive_summary.md"

    subprocess.run(
        [
            sys.executable,
            "scripts/false_positive_smoke.py",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        check=True,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["total_cases"] >= 7
    assert payload["status"] in {"ok", "warning"}
    assert out_md.exists()
