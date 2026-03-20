from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_e2e_golden_smoke_script_runs_and_reports_all_scenarios(tmp_path):
    out_dir = tmp_path / "e2e_golden"
    completed = subprocess.run(
        [sys.executable, "scripts/e2e_golden_smoke.py", "--base-dir", str(out_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    summary_path = Path(payload["summary_path"])
    assert summary_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert set(summary) == {"healthy", "partial", "stale", "degraded_x"}
    assert all(summary[name]["ok"] is True for name in summary)

    assert summary["healthy"]["runtime_signal_origin"] == "historical_replay_jsonl"
    assert summary["healthy"]["replay_data_status"] == "historical"
    assert summary["partial"]["partial_evidence_flag"] is True
    assert summary["partial"]["replay_data_status"] == "historical_partial"
    assert summary["stale"]["stale_provenance_visible"] is True
    assert summary["degraded_x"]["x_status"] == "degraded"
    assert summary["degraded_x"]["x_validation_score"] == 45
    assert summary["degraded_x"]["x_validation_delta"] == 0

    for name in summary:
        for key in (
            "signals_path",
            "trades_path",
            "positions_path",
            "trade_feature_matrix_path",
            "summary_path",
            "manifest_path",
            "analyzer_summary_path",
        ):
            assert Path(summary[name][key]).exists(), f"{name}: missing {key}"
