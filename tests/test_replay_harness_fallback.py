from __future__ import annotations

from pathlib import Path

from src.replay.historical_replay_harness import run_historical_replay

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "historical_replay"


def test_historical_replay_marks_partial_unresolved_histories(tmp_path):
    result = run_historical_replay(
        artifact_dir=FIXTURES / "partial_missing_exit",
        run_id="unit_partial",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
    )

    summary = result["summary"]
    trade = result["artifacts"].trades[0]
    assert summary["partial_rows"] == 1
    assert summary["unresolved_rows"] == 1
    assert trade["replay_resolution_status"] == "partial"
    assert "truncated_price_path" in trade["exit_warnings"]


def test_historical_replay_can_use_explicit_synthetic_smoke_fallback(tmp_path):
    result = run_historical_replay(
        artifact_dir=tmp_path / "missing_artifacts",
        run_id="unit_synthetic_smoke",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
        allow_synthetic_smoke=True,
    )

    assert result["summary"]["synthetic_fallback_used"] is True
    assert result["summary"]["replay_mode"] == "synthetic_smoke"
