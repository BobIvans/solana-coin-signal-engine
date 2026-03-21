from __future__ import annotations

import json
from pathlib import Path


def test_trade_feature_matrix_schema_exposes_richer_contract_fields() -> None:
    schema = json.loads(Path("schemas/trade_feature_matrix.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]

    expected = {
        "schema_version",
        "final_score_pre_wallet",
        "partial_evidence_penalty",
        "low_confidence_evidence_penalty",
        "wallet_weighting_requested_mode",
        "wallet_weighting_effective_mode",
        "wallet_score_component_raw",
        "wallet_score_component_applied",
        "wallet_score_component_applied_shadow",
        "wallet_score_component_capped",
        "wallet_score_component_reason",
        "wallet_registry_status",
        "score_contract_version",
        "replay_score_source",
        "wallet_mode_parity_status",
        "historical_input_hash",
        "smart_wallet_family_ids",
        "smart_wallet_independent_family_ids",
        "smart_wallet_family_unique_count",
        "smart_wallet_independent_family_unique_count",
        "smart_wallet_family_confidence_max",
        "smart_wallet_family_member_count_max",
        "smart_wallet_family_origins",
        "smart_wallet_family_statuses",
        "smart_wallet_family_reason_codes",
        "smart_wallet_family_shared_funder_flag",
        "smart_wallet_family_creator_link_flag",
        "evidence_coverage_ratio",
        "evidence_available",
        "evidence_scores",
        "recommended_position_pct",
        "base_position_pct",
        "effective_position_pct",
        "sizing_multiplier",
        "sizing_reason_codes",
        "sizing_confidence",
        "sizing_origin",
        "sizing_warning",
        "evidence_quality_score",
        "evidence_conflict_flag",
        "partial_evidence_flag"
    }

    missing = sorted(field for field in expected if field not in props)
    assert not missing, f"Missing schema properties: {missing}"


def test_trade_feature_matrix_schema_requires_schema_version() -> None:
    schema = json.loads(Path("schemas/trade_feature_matrix.schema.json").read_text(encoding="utf-8"))
    required = set(schema.get("required", []))
    assert "schema_version" in required


def test_trade_feature_matrix_schema_is_closed_on_top_level() -> None:
    schema = json.loads(Path("schemas/trade_feature_matrix.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False


def test_trade_feature_matrix_schema_exposes_canonical_runtime_replay_fields() -> None:
    schema = json.loads(Path("schemas/trade_feature_matrix.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    for field in {
        "token_address",
        "decision",
        "regime_decision",
        "replay_input_origin",
        "replay_data_status",
        "replay_resolution_status",
        "wallet_weighting_requested_mode",
        "wallet_weighting_effective_mode",
        "replay_score_source",
        "wallet_mode_parity_status",
        "historical_input_hash",
        "score_contract_version",
    }:
        assert field in props
