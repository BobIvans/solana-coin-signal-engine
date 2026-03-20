from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import validate

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


def _entry_row() -> dict:
    return {
        "token_address": "mint-test-1",
        "entry_decision": "SCALP",
        "entry_confidence": 0.72,
        "recommended_position_pct": 0.25,
        "entry_reason": "bundle_plus_buy_pressure",
        "regime_confidence": 0.70,
        "regime_reason_flags": ["bundle_supportive"],
        "regime_blockers": [],
        "expected_hold_class": "seconds_to_minutes",
        "entry_snapshot": {"bundle_cluster_score": 0.66},
        "entry_flags": [],
    }


def _enriched_row() -> dict:
    return {
        "token_address": "mint-test-1",
        "enrichment_status": "ok",
        "contract_version": "enriched_v_test",
        "enriched_at": "2026-03-20T10:00:00Z",
        "top20_holder_share": 0.33,
        "first50_holder_conc_est": 0.48,
        "holder_entropy_est": 0.77,
        "smart_wallet_hits": 3,
        "dev_sell_pressure_5m": 0.01,
        "bundle_count_first_60s": 2,
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
        "bundle_evidence_status": "complete",
        "bundle_evidence_source": "bundle_layer",
        "bundle_evidence_confidence": "high",
        "bundle_evidence_warning": "",
        "bundle_metric_origin": "direct_evidence",
        "cluster_evidence_status": "complete",
        "cluster_evidence_source": "graph",
        "cluster_evidence_confidence": "high",
        "cluster_metric_origin": "graph_evidence",
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
        "linkage_metric_origin": "heuristic_evidence",
        "linkage_status": "partial",
        "linkage_warning": "",
        "net_unique_buyers_60s": 11,
        "liquidity_refill_ratio_120s": 1.20,
        "cluster_sell_concentration_120s": 0.18,
        "smart_wallet_dispersion_score": 0.42,
        "x_author_velocity_5m": 1.1,
        "seller_reentry_ratio": 0.35,
        "liquidity_shock_recovery_sec": 42,
        "continuation_status": "complete",
        "continuation_warning": "",
        "continuation_confidence": "high",
        "continuation_metric_origin": "mixed_evidence",
        "continuation_coverage_ratio": 1.0,
        "continuation_inputs_status": {"tx": "ok", "x": "ok", "wallet_registry": "ok"},
        "continuation_warnings": [],
        "continuation_available_evidence": ["tx", "x", "wallet_registry"],
        "continuation_missing_evidence": [],
    }


def _build_repo_fixture(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        """# Repo\n\nArtifacts: `shortlist.json`, `x_validated.json`, `enriched_tokens.json`, `rug_assessed_tokens.json`, `scored_tokens.json`, `entry_candidates.json`, `trade_feature_matrix.jsonl`, `post_run_summary.json`, `post_run_recommendations.json`.\n\nTools: `tools/contract_parity.py`, `tools/docs_sync_audit.py`, `scripts/contract_parity_smoke.py`, `docs/contracts.md`.\n""",
        encoding="utf-8",
    )
    (root / "docs" / "contracts.md").write_text(
        """# Contracts\n\ncore_shortlist\ncore_x_validation\ncore_enriched\nbundle_cluster\nbundle_provenance\ncluster_provenance\nlinkage_evidence\ncontinuation\ncore_rug_assessed\ncore_scored\ncore_entry_candidates\nreplay_feature_matrix\npost_run_summary\npost_run_recommendations\n\nArtifacts: `shortlist.json`, `x_validated.json`, `enriched_tokens.json`, `rug_assessed_tokens.json`, `scored_tokens.json`, `entry_candidates.json`, `trade_feature_matrix.jsonl`, `post_run_summary.json`, `post_run_recommendations.json`.\n\nTools: `tools/contract_parity.py`, `tools/docs_sync_audit.py`, `scripts/contract_parity_smoke.py`, `docs/contracts.md`.\n""",
        encoding="utf-8",
    )

    processed = root / "data" / "processed"
    _write_json(processed / "shortlist.json", {"contract_version": "shortlist_v_test", "tokens": [{"token_address": "mint-test-1", "symbol": "TST"}]})
    _write_json(processed / "x_validated.json", {"contract_version": "x_v_test", "tokens": [{"token_address": "mint-test-1", "x_status": "ok", "x_validation_score": 74.0}]})
    _write_json(processed / "enriched_tokens.json", {"contract_version": "enriched_v_test", "generated_at": "2026-03-20T10:00:00Z", "tokens": [_enriched_row()]})
    _write_json(processed / "rug_assessed_tokens.json", {"contract_version": "rug_v_test", "tokens": [{"token_address": "mint-test-1", "rug_score": 0.11, "rug_status": "PASS", "rug_flags": [], "rug_warnings": []}]})
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
                    "score_flags": [],
                    "score_warnings": [],
                }
            ],
        },
    )
    _write_json(processed / "entry_candidates.json", {"contract_version": "entry_v_test", "tokens": [_entry_row()]})
    _write_json(
        processed / "post_run_summary.json",
        {
            "as_of": "2026-03-20T10:00:00Z",
            "contract_version": "post_run_v_test",
            "warnings": [],
            "matrix_analysis_available": True,
            "matrix_row_count": 1,
            "trade_feature_matrix_path": str(root / "trade_feature_matrix.jsonl"),
            "friction_summary": {"avg_slippage_bps": 150},
        },
    )
    _write_json(
        processed / "post_run_recommendations.json",
        {
            "contract_version": "post_run_v_test",
            "recommendations": [{"kind": "keep_shadow_mode", "confidence": 0.7}],
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
                "liquidity_shock_recovery_sec": 42,
                "regime_confidence": 0.70,
                "bundle_tip_efficiency": 0.62,
            }
        ],
    )


def test_contract_parity_happy_path(tmp_path: Path) -> None:
    _build_repo_fixture(tmp_path)
    report = compute_contract_parity_report(tmp_path, include_docs_sync=True)
    assert report["summary"]["overall_status"] == "ok"
    assert report["summary"]["mismatch_count"] == 0
    assert report["summary"]["missing_count"] == 0
    assert report["docs_sync"]["status"] == "ok"
    assert any(event["event"] == "contract_group_checked" for event in report["events"])

    schema = json.loads((REPO_ROOT / "schemas" / "contract_parity_report.schema.json").read_text(encoding="utf-8"))
    validate(instance=report, schema=schema)
