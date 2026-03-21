import json
import subprocess
import sys
from pathlib import Path


def test_replay_writes_required_artifacts_and_fields():
    run_id = "outputs_run"
    subprocess.run(
        [
            sys.executable,
            "scripts/replay_7d.py",
            "--artifact-dir",
            "tests/fixtures/historical_replay/full_win",
            "--config",
            "config/replay.default.yaml",
            "--days",
            "7",
            "--seed",
            "42",
            "--run-id",
            run_id,
            "--dry-run",
        ],
        check=True,
    )
    base = Path("runs") / run_id
    required = [
        "manifest.json",
        "universe.jsonl",
        "backfill.jsonl",
        "signals.jsonl",
        "trades.jsonl",
        "trade_feature_matrix.jsonl",
        "positions.json",
        "replay_summary.json",
        "replay_summary.md",
    ]
    for name in required:
        assert (base / name).exists(), name

    signal = json.loads((base / "signals.jsonl").read_text().splitlines()[0])
    for key in ["run_id", "ts", "token_address", "pair_address", "decision", "x_status", "x_validation_score", "features", "wallet_weighting_requested_mode", "wallet_weighting_effective_mode", "replay_score_source", "wallet_mode_parity_status", "historical_input_hash"]:
        assert key in signal

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["wallet_weighting_requested_mode"] == "off"
    assert manifest["artifact_truth_layer"] == "trade_feature_matrix.jsonl"
    assert manifest["replay_score_source"] == "generic_scored_artifact_rescored"
    assert manifest["wallet_mode_parity_status"] == "comparable"
    assert manifest["historical_input_hash"]

    matrix_row = json.loads((base / "trade_feature_matrix.jsonl").read_text().splitlines()[0])
    for key in ["run_id", "ts", "token_address", "pair_address", "symbol", "config_hash", "decision", "entry_confidence", "recommended_position_pct", "final_score_pre_wallet", "wallet_weighting_requested_mode", "wallet_weighting_effective_mode", "wallet_score_component_raw", "wallet_score_component_applied", "wallet_score_component_applied_shadow", "replay_score_source", "wallet_mode_parity_status", "score_contract_version", "historical_input_hash", "replay_input_origin", "replay_data_status", "replay_resolution_status", "schema_version"]:
        assert key in matrix_row
