from __future__ import annotations

from pathlib import Path

from src.replay.historical_replay_harness import run_historical_replay

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "historical_replay"


def test_historical_replay_reconstructs_resolved_winning_trade(tmp_path):
    result = run_historical_replay(
        artifact_dir=FIXTURES / "full_win",
        run_id="unit_full_win",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
    )

    summary = result["summary"]
    trade = result["artifacts"].trades[0]
    row = result["artifacts"].trade_feature_matrix[0]

    assert summary["historical_rows_used"] == 1
    assert summary["partial_rows"] == 0
    assert summary["wallet_weighting_requested_mode"] == "off"
    assert summary["replay_score_source"] == "generic_scored_artifact_rescored"
    assert summary["wallet_mode_parity_status"] == "comparable"
    assert summary["historical_input_hash"]
    assert trade["replay_resolution_status"] == "resolved"
    assert trade["replay_score_source"] == "generic_scored_artifact_rescored"
    assert trade["wallet_mode_parity_status"] == "comparable"
    assert trade["net_pnl_pct"] > 0
    assert row["replay_input_origin"] == "historical"
    assert row["replay_data_status"] == "historical"
    assert row["replay_score_source"] == "generic_scored_artifact_rescored"
    assert row["wallet_mode_parity_status"] == "comparable"
    assert row["historical_input_hash"] == summary["historical_input_hash"]
    assert row["synthetic_assist_flag"] is False


def test_historical_replay_reconstructs_resolved_losing_trade(tmp_path):
    result = run_historical_replay(
        artifact_dir=FIXTURES / "full_loss",
        run_id="unit_full_loss",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
    )

    trade = result["artifacts"].trades[0]
    assert trade["replay_resolution_status"] == "resolved"
    assert trade["net_pnl_pct"] < 0
    assert trade["exit_reason_final"] in {"trend_hard_stop", "scalp_stop_loss"}
