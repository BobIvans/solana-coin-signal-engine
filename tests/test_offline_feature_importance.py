from __future__ import annotations

import json
from pathlib import Path

from analytics.feature_groups import feature_group_for_name, group_features
from analytics.offline_feature_importance import (
    compute_offline_feature_importance,
    load_feature_matrix,
    summarize_feature_importance,
    write_feature_importance_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "offline_feature_importance"
SCHEMA_PATH = ROOT / "schemas" / "offline_feature_importance.schema.json"


def test_feature_groups_map_expected_prefixes():
    assert feature_group_for_name("bundle_count_first_60s") == "bundle_features"
    assert feature_group_for_name("cluster_concentration_ratio") == "cluster_features"
    assert feature_group_for_name("net_unique_buyers_60s") == "continuation_features"
    assert feature_group_for_name("wallet_weighting") == "wallet_features"
    assert feature_group_for_name("x_author_velocity_5m") == "x_features"
    assert feature_group_for_name("regime_confidence") == "regime_features"
    assert feature_group_for_name("hold_sec") == "outcome_only_fields"
    assert feature_group_for_name("linkage_risk_score") == "linkage_features"
    assert feature_group_for_name("liquidity_usd") == "friction_features"
    grouped = group_features(["bundle_count_first_60s", "cluster_concentration_ratio"])
    assert grouped["bundle_features"] == ["bundle_count_first_60s"]


def test_offline_feature_importance_generates_rankings_and_matches_schema_shape(tmp_path):
    matrix = load_feature_matrix(FIXTURES / "healthy_mixed_replay_matrix.jsonl")
    payload = compute_offline_feature_importance(matrix, generated_at="2026-03-20T00:00:00Z")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    required_fields = set(schema["required"])
    assert required_fields.issubset(payload.keys())
    assert payload["analysis_only"] is True
    assert payload["not_for_online_decisioning"] is True
    assert payload["input_artifact"]["excluded_row_count"] == 0
    profitable = next(item for item in payload["targets"] if item["target_name"] == "profitable_trade_flag")
    assert profitable["per_feature_importance"][0]["importance_score"] >= profitable["per_feature_importance"][-1]["importance_score"]
    assert profitable["grouped_importance"]

    outputs = write_feature_importance_outputs(payload, tmp_path)
    assert Path(outputs["json_path"]).exists()
    assert Path(outputs["markdown_path"]).exists()
    markdown = summarize_feature_importance(payload)
    assert "analysis-only" in markdown.lower()
    assert "top feature groups" in markdown.lower()


def test_sparse_and_malformed_inputs_report_missingness_and_exclusions():
    sparse_payload = compute_offline_feature_importance(load_feature_matrix(FIXTURES / "sparse_missing_replay_matrix.jsonl"))
    profitable = next(item for item in sparse_payload["targets"] if item["target_name"] == "profitable_trade_flag")
    assert any("low coverage" in " ".join(feature["warnings"]) for feature in profitable["per_feature_importance"])

    malformed_matrix = load_feature_matrix(FIXTURES / "malformed_replay_matrix.jsonl")
    malformed_payload = compute_offline_feature_importance(malformed_matrix)
    assert malformed_payload["input_artifact"]["excluded_row_count"] >= 2
    assert malformed_payload["input_artifact"]["malformed_row_count"] == 1


def test_low_sample_and_grouped_sanity_fixtures_emit_cautions_and_groups():
    low_sample_payload = compute_offline_feature_importance(load_feature_matrix(FIXTURES / "low_sample_target_replay_matrix.jsonl"))
    trend_target = next(item for item in low_sample_payload["target_definitions"] if item["target_name"] == "trend_success_flag")
    assert trend_target["warnings"]

    grouped_payload = compute_offline_feature_importance(load_feature_matrix(FIXTURES / "grouped_importance_sanity_replay_matrix.jsonl"))
    profitable = next(item for item in grouped_payload["targets"] if item["target_name"] == "profitable_trade_flag")
    group_names = {item["feature_group"] for item in profitable["grouped_importance"]}
    assert {"bundle_features", "cluster_features", "x_features", "wallet_features"}.issubset(group_names)


def test_fast_failure_fixture_surfaces_risk_associated_features():
    payload = compute_offline_feature_importance(load_feature_matrix(FIXTURES / "fast_failure_pattern_replay_matrix.jsonl"))
    fast_failure = next(item for item in payload["targets"] if item["target_name"] == "fast_failure_flag")
    top_features = [item["feature_name"] for item in fast_failure["per_feature_importance"][:5]]
    assert "cluster_concentration_ratio" in top_features
    assert any(group["feature_group"] == "cluster_features" for group in fast_failure["grouped_importance"])

def test_outcome_fields_are_excluded_from_feature_space():
    from analytics.offline_feature_importance import _infer_feature_names

    matrix = load_feature_matrix(FIXTURES / "healthy_mixed_replay_matrix.jsonl")
    feature_names = set(_infer_feature_names(matrix["rows"]))
    banned = {
        "net_pnl_pct",
        "gross_pnl_pct",
        "hold_sec",
        "exit_reason_final",
        "mfe_pct",
        "mae_pct",
        "mfe_pct_240s",
        "mae_pct_240s",
        "trend_survival_15m",
        "trend_survival_60m",
        "time_to_first_profit_sec",
    }
    assert feature_names.isdisjoint(banned)


def test_payload_exposes_excluded_outcome_fields():
    payload = compute_offline_feature_importance(load_feature_matrix(FIXTURES / "healthy_mixed_replay_matrix.jsonl"))
    excluded = set(payload["excluded_feature_names"])
    assert "hold_sec" in excluded
    assert "net_pnl_pct" in excluded
    assert "trend_survival_15m" in excluded
