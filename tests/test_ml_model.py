from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from analytics.ml_model import MLTrainingConfig, build_training_dataframe, load_trade_feature_matrix, train_model, write_ml_outputs


REQUIRED_SUMMARY_KEYS = {
    "schema_version",
    "model_type",
    "target_name",
    "train_row_count",
    "feature_names",
    "top_feature_importance",
    "evaluation_metrics",
    "training_skipped",
}


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _make_matrix_rows(row_count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        profitable = index % 2 == 0
        rows.append(
            {
                "position_id": f"pos_{index}",
                "token_address": f"token_{index}",
                "ts": f"2026-03-19T00:{index:02d}:00Z",
                "final_score": 92.0 if profitable else 58.0,
                "regime_decision": "TREND" if profitable else "SCALP",
                "regime_confidence": 0.84 if profitable else 0.42,
                "expected_hold_class": "trend" if profitable else (None if index % 5 == 0 else "scalp"),
                "onchain_core": 30.0 if profitable else 12.0,
                "early_signal_bonus": 5.0 if profitable else 1.0,
                "x_validation_bonus": 3.0 if profitable else 0.0,
                "rug_penalty": 0.0 if profitable else 3.5,
                "spam_penalty": 0.0 if profitable else 1.5,
                "confidence_adjustment": 1.2 if profitable else -0.2,
                "wallet_adjustment": 1.0 if profitable else -0.5,
                "bundle_aggression_bonus": 3.5 if profitable else 0.4,
                "organic_multi_cluster_bonus": 2.0 if profitable else 0.0,
                "single_cluster_penalty": 0.0 if profitable else 2.4,
                "creator_cluster_penalty": 0.0 if profitable else 1.2,
                "bundle_sell_heavy_penalty": 0.0 if profitable else 1.1,
                "retry_manipulation_penalty": 0.1 if profitable else 1.6,
                "bundle_count_first_60s": 6 if profitable else 2,
                "bundle_size_value": 12000.0 if profitable else 2400.0,
                "unique_wallets_per_bundle_avg": 3.0 if profitable else 1.0,
                "bundle_timing_from_liquidity_add_min": 0.4 if profitable else 2.0,
                "bundle_success_rate": 0.81 if profitable else (None if index % 4 == 0 else 0.18),
                "bundle_composition_dominant": "buy-only" if profitable else "sell-heavy",
                "bundle_tip_efficiency": 0.7 if profitable else 0.2,
                "bundle_failure_retry_pattern": None if index % 3 == 0 else ("low" if profitable else "high"),
                "cross_block_bundle_correlation": 0.22 if profitable else 0.74,
                "bundle_wallet_clustering_score": 0.28 if profitable else 0.89,
                "cluster_concentration_ratio": 0.32 if profitable else 0.93,
                "num_unique_clusters_first_60s": 4 if profitable else 1,
                "creator_in_cluster_flag": False if profitable else True,
                "liquidity_usd": 28000.0 if profitable else 6000.0,
                "buy_pressure_entry": 0.91 if profitable else 0.35,
                "volume_velocity_entry": 4.8 if profitable else 1.2,
                "holder_growth_5m_entry": 21 if profitable else 4,
                "smart_wallet_hits_entry": 5 if profitable else 0,
                "smart_wallet_score_sum": 16.0 if profitable else 2.0,
                "smart_wallet_tier1_hits": 2 if profitable else 0,
                "smart_wallet_early_entry_hits": 2 if profitable else 0,
                "smart_wallet_netflow_bias": 0.45 if profitable else -0.3,
                "x_validation_score_entry": 78.0 if profitable else (None if index % 6 == 0 else 38.0),
                "x_validation_delta_entry": 10.0 if profitable else -6.0,
                "x_status": "ok" if profitable else (None if index % 7 == 0 else "degraded"),
                "net_pnl_pct": 18.0 if profitable else -9.0,
                "gross_pnl_pct": 20.0 if profitable else -7.5,
                "hold_sec": 720 if profitable else 90,
                "mfe_pct": 24.0 if profitable else 2.0,
                "mae_pct": -4.0 if profitable else -12.0,
                "exit_reason_final": "trend_take_profit" if profitable else "scalp_stop_loss",
            }
        )
    return rows


def test_train_bundle_cluster_model_script_gracefully_skips_when_matrix_missing(tmp_path):
    output_dir = tmp_path / "run_missing"
    command = [
        sys.executable,
        "scripts/train_bundle_cluster_model.py",
        "--matrix-path",
        str(tmp_path / "does_not_exist.jsonl"),
        "--output-dir",
        str(output_dir),
        "--min-train-rows",
        "5",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)

    summary = json.loads((output_dir / "ml_model_summary.json").read_text(encoding="utf-8"))
    assert payload["training_skipped"] is True
    assert summary["training_skipped"] is True
    assert summary["skip_reason"] == "matrix_input_missing"
    assert json.loads((output_dir / "ml_feature_importance.json").read_text(encoding="utf-8"))["feature_importance"] == []


def test_train_model_skips_when_insufficient_samples(tmp_path):
    matrix_path = tmp_path / "trade_feature_matrix.jsonl"
    _write_jsonl(matrix_path, _make_matrix_rows(6))

    loaded = load_trade_feature_matrix([matrix_path])
    result = train_model(loaded.rows, MLTrainingConfig(min_train_rows=12))

    assert result["training_skipped"] is True
    assert result["skip_reason"] == "insufficient_samples"
    assert result["train_row_count"] == 6
    assert result["label_distribution"] == {"negative": 3, "positive": 3}


def test_train_model_writes_summary_feature_importance_and_predictions(tmp_path):
    matrix_path = tmp_path / "trade_feature_matrix.jsonl"
    rows = _make_matrix_rows(18)
    _write_jsonl(matrix_path, rows)

    loaded = load_trade_feature_matrix([matrix_path])
    result = train_model(
        loaded.rows,
        MLTrainingConfig(min_train_rows=12, enable_predictions_output=True),
    )

    assert result["training_skipped"] is False
    assert result["target_name"] == "profitable_trade_flag"
    assert REQUIRED_SUMMARY_KEYS.issubset(result.keys())
    assert result["evaluation_metrics"]["validation_row_count"] > 0
    assert result["top_feature_importance"]
    assert any(item["feature_name"] == "final_score" for item in result["feature_importance"])
    assert any(item["feature_name"] == "regime_decision" for item in result["feature_importance"])

    output_paths = write_ml_outputs(result, tmp_path / "run_a", model_dir=tmp_path / "models")
    summary = json.loads(Path(output_paths["summary_path"]).read_text(encoding="utf-8"))
    importance = json.loads(Path(output_paths["feature_importance_path"]).read_text(encoding="utf-8"))
    predictions = [
        json.loads(line)
        for line in Path(output_paths["predictions_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert REQUIRED_SUMMARY_KEYS.issubset(summary.keys())
    assert summary["training_skipped"] is False
    assert importance["training_skipped"] is False
    assert importance["feature_importance"]
    assert Path(output_paths["model_path"]).exists()
    assert Path(output_paths["model_meta_path"]).exists()
    assert predictions
    assert all("predicted_probability" in row for row in predictions)


def test_preprocessing_handles_missing_categorical_and_numeric_values(tmp_path):
    matrix_path = tmp_path / "trade_feature_matrix.jsonl"
    rows = _make_matrix_rows(14)
    rows[0]["bundle_composition_dominant"] = None
    rows[1]["final_score"] = None
    rows[2]["x_status"] = None
    rows[3]["bundle_failure_retry_pattern"] = None
    _write_jsonl(matrix_path, rows)

    loaded = load_trade_feature_matrix([matrix_path])
    result = train_model(loaded.rows, MLTrainingConfig(min_train_rows=10))

    assert result["training_skipped"] is False
    assert result["feature_stats"]["final_score"]["missing_count"] >= 1
    assert result["feature_stats"]["bundle_composition_dominant"]["missing_count"] >= 1
    assert result["feature_stats"]["x_status"]["missing_count"] >= 1


def test_build_training_dataframe_excludes_post_trade_leakage_fields():
    feature_rows, labels, _ = build_training_dataframe(_make_matrix_rows(8), "profitable_trade_flag")

    assert labels
    assert feature_rows
    forbidden = {
        "net_pnl_pct",
        "gross_pnl_pct",
        "hold_sec",
        "exit_reason_final",
        "mfe_pct",
        "mae_pct",
    }
    assert forbidden.isdisjoint(feature_rows[0].keys())
