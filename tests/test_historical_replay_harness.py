from __future__ import annotations

import json
import shutil
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
    assert summary["artifact_truth_layer"] == "trade_feature_matrix.jsonl"
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



def test_historical_replay_uses_backfill_embedded_price_paths(tmp_path):
    artifact_dir = tmp_path / "backfill_embedded"
    shutil.copytree(FIXTURES / "full_win", artifact_dir)
    (artifact_dir / "price_paths.json").unlink()
    source_paths = json.loads((FIXTURES / "full_win" / "price_paths.json").read_text(encoding="utf-8"))
    backfill_row = {
        "token_address": "tok_full_win",
        "pair_address": "pair_full_win",
        "price_paths": source_paths,
    }
    (artifact_dir / "chain_backfill.jsonl").write_text(json.dumps(backfill_row) + "\n", encoding="utf-8")

    result = run_historical_replay(
        artifact_dir=artifact_dir,
        run_id="unit_backfill_embedded",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
    )

    trade = result["artifacts"].trades[0]
    assert trade["replay_resolution_status"] == "resolved"
    assert "missing_price_path" not in (trade.get("exit_warnings") or [])



def test_historical_replay_marks_truncated_backfill_price_paths_partial(tmp_path):
    artifact_dir = tmp_path / "backfill_truncated"
    shutil.copytree(FIXTURES / "full_win", artifact_dir)
    (artifact_dir / "price_paths.json").unlink()
    backfill_row = {
        "token_address": "tok_full_win",
        "pair_address": "pair_full_win",
        "price_paths": [{
            "token_address": "tok_full_win",
            "pair_address": "pair_full_win",
            "price_path": [
                {"offset_sec": 0, "price": 1.0, "timestamp": "2026-03-10T12:00:00Z"},
                {"offset_sec": 20, "price": 1.11, "timestamp": "2026-03-10T12:00:20Z"},
            ],
            "truncated": True,
            "missing": False,
            "price_path_status": "partial",
        }],
    }
    (artifact_dir / "chain_backfill.jsonl").write_text(json.dumps(backfill_row) + "\n", encoding="utf-8")

    result = run_historical_replay(
        artifact_dir=artifact_dir,
        run_id="unit_backfill_truncated",
        config_path=ROOT / "config" / "replay.default.yaml",
        output_base_dir=tmp_path,
        dry_run=True,
    )

    trade = result["artifacts"].trades[0]
    assert trade["replay_resolution_status"] in {"partial", "unresolved"}
    assert "truncated_price_path" in (trade.get("exit_warnings") or [])