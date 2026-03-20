from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.contract_parity import compute_contract_parity_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _build_repo_fixture(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        """# Repo\n\nArtifacts: `shortlist.json`, `enriched_tokens.json`, `rug_assessed_tokens.json`, `scored_tokens.json`, `entry_candidates.json`, `trade_feature_matrix.jsonl`, `post_run_summary.json`, `post_run_recommendations.json`, `legacy_output.json`.\n\n<<<<<<< HEAD\n""",
        encoding="utf-8",
    )
    (root / "docs" / "contracts.md").write_text(
        """# Contracts\n\ncore_shortlist\ncore_x_validation\ncore_enriched\nbundle_cluster\nbundle_provenance\ncluster_provenance\nlinkage_evidence\ncontinuation\ncore_rug_assessed\ncore_scored\ncore_entry_candidates\nreplay_feature_matrix\npost_run_summary\npost_run_recommendations\n\nArtifacts: `shortlist.json`, `enriched_tokens.json`, `rug_assessed_tokens.json`, `scored_tokens.json`, `entry_candidates.json`, `trade_feature_matrix.jsonl`, `post_run_summary.json`, `post_run_recommendations.json`.\n""",
        encoding="utf-8",
    )

    processed = root / "data" / "processed"
    _write_json(processed / "shortlist.json", {"contract_version": "shortlist_v_test", "tokens": [{"token_address": "mint-test-1"}]})
    # x_validated.json intentionally missing
    _write_json(
        processed / "enriched_tokens.json",
        {
            "contract_version": "enriched_v_test",
            "generated_at": "2026-03-20T10:00:00Z",
            "tokens": [
                {
                    "token_address": "mint-test-1",
                    "enrichment_status": "ok",
                    "contract_version": "enriched_v_test",
                    "enriched_at": "2026-03-20T10:00:00Z",
                    # missing bundle_count_first_60s on purpose
                    "bundle_size_value": 155.0,
                    "unique_wallets_per_bundle_avg": 2.0,
                    "bundle_timing_from_liquidity_add_min": 0.2,
                    "bundle_success_rate": 0.75,
                    "bundle_composition_dominant": "buy_heavy",
                    "bundle_tip_efficiency": 0.62,
                    "bundle_failure_retry_pattern": 1,
                    "cross_block_bundle_correlation": 0.44,
                    "bundle_wallet_clustering_score": 0.58,
                    "cluster_concentration_ratio": 0.36,
                    "num_unique_clusters_first_60s": 3,
                    "creator_in_cluster_flag": False,
                    "bundle_evidence_source": "bundle_layer",
                    "bundle_evidence_confidence": "high",
                    "bundle_evidence_warning": "",
                    "bundle_metric_origin": "raw_bundles",
                    "cluster_evidence_status": "complete",
                    "cluster_evidence_source": "graph",
                    "cluster_evidence_confidence": "high",
                    "graph_cluster_id_count": 3,
                    "graph_cluster_coverage_ratio": 0.91,
                    "creator_cluster_id": "cluster-creator-1",
                    "dominant_cluster_id": "cluster-dominant-1",
                    "creator_dev_link_score": 0.10,
                    "creator_buyer_link_score": 0.08,
                    "dev_buyer_link_score": 0.04,
                    "shared_funder_link_score": 0.12,
                    "creator_cluster_link_score": 0.09,
                    "cluster_dev_link_score": 0.11,
                    "linkage_risk_score": 0.18,
                    "creator_funder_overlap_count": 1,
                    "buyer_funder_overlap_count": 1,
                    "funder_overlap_count": 2,
                    "linkage_reason_codes": ["shared_funder"],
                    "linkage_confidence": "low",
                    "linkage_metric_origin": "heuristic",
                    "linkage_status": "partial",
                    "linkage_warning": "",
                    "net_unique_buyers_60s": 11,
                    "liquidity_refill_ratio_120s": 1.20,
                    "cluster_sell_concentration_120s": 0.18,
                    "smart_wallet_dispersion_score": 0.42,
                    "x_author_velocity_5m": 1.1,
                    "seller_reentry_ratio": 0.35,
                    "liquidity_shock_recovery_sec": 42,
                    "continuation_status": "partial",
                    "continuation_warning": "",
                    "continuation_confidence": "medium",
                    "continuation_metric_origin": "partial",
                    "continuation_coverage_ratio": 0.7,
                    "continuation_inputs_status": {"tx": "ok"},
                    "continuation_warnings": [],
                    "continuation_available_evidence": ["tx"],
                    "continuation_missing_evidence": ["x"],
                    "mystery_extra_field": 123
                }
            ],
        },
    )
    (processed / "rug_assessed_tokens.json").parent.mkdir(parents=True, exist_ok=True)
    (processed / "rug_assessed_tokens.json").write_text("{bad json\n", encoding="utf-8")
    _write_json(
        processed / "scored_tokens.json",
        {
            "contract_version": "score_v_test",
            "tokens": [
                {
                    "token_address": "mint-test-1",
                    "onchain_core": 46.0,
                    "early_signal_bonus": 7.0,
                    "x_validation_bonus": 8.0,
                    "rug_penalty": -2.0,
                    "spam_penalty": 0.0,
                    "confidence_adjustment": 1.0,
                    "final_score": 88.0,
                    "regime_candidate": "ENTRY_CANDIDATE",
                    "mystery_score": 999.0
                }
            ],
        },
    )
    _write_json(
        processed / "entry_candidates.json",
        {
            "contract_version": "entry_v_test",
            "tokens": [
                {
                    "token_address": "mint-test-1",
                    "entry_decision": "SCALP",
                    "entry_confidence": 0.72,
                    "recommended_position_pct": 0.25,
                    "entry_reason": "bundle_plus_buy_pressure",
                    "regime_confidence": 0.70,
                    "regime_reason_flags": ["bundle_supportive"],
                    "regime_blockers": [],
                    "expected_hold_class": "seconds_to_minutes",
                    "entry_snapshot": {"bundle_cluster_score": 0.66}
                }
            ],
        },
    )
    _write_json(
        processed / "post_run_summary.json",
        {
            "as_of": "2026-03-20T10:00:00Z",
            "contract_version": "post_run_v_test",
            "warnings": []
        },
    )
    _write_json(
        processed / "post_run_recommendations.json",
        {
            "contract_version": "post_run_v_test",
            "recommendations": []
        },
    )
    _write_jsonl(
        root / "trade_feature_matrix.jsonl",
        [
            {
                "position_id": "pos_1",
                "regime_decision": "SCALP",
                "expected_hold_class": "seconds_to_minutes",
                "x_status": "ok",
                "exit_reason_final": "take_profit",
                "hold_sec": 42,
                "net_pnl_pct": 6.2,
                "bundle_count_first_60s": 2,
                "bundle_size_value": 155.0,
                "net_unique_buyers_60s": 11,
                "liquidity_refill_ratio_120s": 1.20,
                "cluster_sell_concentration_120s": 0.18,
                "smart_wallet_dispersion_score": 0.42,
                "x_author_velocity_5m": 1.1,
                "seller_reentry_ratio": 0.35,
                "liquidity_shock_recovery_sec": 42
            }
        ],
    )


def test_contract_parity_mismatch_visibility(tmp_path: Path) -> None:
    _build_repo_fixture(tmp_path)
    report = compute_contract_parity_report(tmp_path, include_docs_sync=True)

    statuses = {
        (entry["contract_group"], entry["artifact_name"]): entry
        for entry in report["contract_groups"]
    }

    assert statuses[("bundle_cluster", "enriched_tokens")]["status"] == "mismatch"
    assert "bundle_count_first_60s" in statuses[("bundle_cluster", "enriched_tokens")]["missing_required_fields"]
    assert "mystery_extra_field" in statuses[("bundle_cluster", "enriched_tokens")]["extra_fields"]

    assert statuses[("bundle_provenance", "enriched_tokens")]["status"] == "mismatch"
    assert "bundle_evidence_status" in statuses[("bundle_provenance", "enriched_tokens")]["missing_required_fields"]

    assert statuses[("cluster_provenance", "enriched_tokens")]["status"] == "mismatch"
    assert "cluster_metric_origin" in statuses[("cluster_provenance", "enriched_tokens")]["missing_required_fields"]

    assert statuses[("linkage_evidence", "enriched_tokens")]["status"] in {"ok", "warning"}
    assert statuses[("linkage_evidence", "enriched_tokens")]["missing_required_fields"] == []

    assert statuses[("core_x_validation", "x_validated")]["status"] == "missing"
    assert statuses[("core_rug_assessed", "rug_assessed_tokens")]["status"] == "malformed"
    assert statuses[("core_scored", "scored_tokens")]["status"] == "warning"
    assert "mystery_score" in statuses[("core_scored", "scored_tokens")]["extra_fields"]

    assert report["docs_sync"]["status"] == "mismatch"
    assert report["summary"]["overall_status"] in {"missing", "malformed"}

    event_types = {event["event"] for event in report["events"]}
    assert "artifact_missing" in event_types
    assert "artifact_malformed" in event_types
    assert "required_fields_missing" in event_types
    assert "extra_fields_detected" in event_types
