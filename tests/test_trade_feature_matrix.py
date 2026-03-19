from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MATRIX_KEYS = [
    "run_id",
    "ts",
    "token_address",
    "pair_address",
    "symbol",
    "config_hash",
    "decision",
    "entry_decision",
    "regime_decision",
    "regime_confidence",
    "regime_reason_flags",
    "regime_blockers",
    "expected_hold_class",
    "entry_confidence",
    "recommended_position_pct",
    "final_score",
    "onchain_core",
    "early_signal_bonus",
    "x_validation_bonus",
    "rug_penalty",
    "spam_penalty",
    "confidence_adjustment",
    "wallet_adjustment",
    "bundle_aggression_bonus",
    "organic_multi_cluster_bonus",
    "single_cluster_penalty",
    "creator_cluster_penalty",
    "bundle_sell_heavy_penalty",
    "retry_manipulation_penalty",
    "age_sec",
    "age_minutes",
    "liquidity_usd",
    "buy_pressure_entry",
    "volume_velocity_entry",
    "holder_growth_5m_entry",
    "smart_wallet_hits_entry",
    "net_unique_buyers_60s",
    "liquidity_refill_ratio_120s",
    "cluster_sell_concentration_120s",
    "smart_wallet_dispersion_score",
    "x_author_velocity_5m",
    "seller_reentry_ratio",
    "liquidity_shock_recovery_sec",
    "x_status",
    "x_validation_score_entry",
    "x_validation_delta_entry",
    "bundle_count_first_60s",
    "bundle_size_value",
    "unique_wallets_per_bundle_avg",
    "bundle_timing_from_liquidity_add_min",
    "bundle_success_rate",
    "bundle_composition_dominant",
    "bundle_tip_efficiency",
    "bundle_failure_retry_pattern",
    "cross_block_bundle_correlation",
    "bundle_wallet_clustering_score",
    "cluster_concentration_ratio",
    "num_unique_clusters_first_60s",
    "creator_in_cluster_flag",
    "smart_wallet_score_sum",
    "smart_wallet_tier1_hits",
    "smart_wallet_tier2_hits",
    "smart_wallet_unique_count",
    "smart_wallet_early_entry_hits",
    "smart_wallet_netflow_bias",
    "exit_decision",
    "exit_reason_final",
    "exit_flags",
    "exit_warnings",
    "hold_sec",
    "gross_pnl_pct",
    "net_pnl_pct",
    "mfe_pct",
    "mae_pct",
    "wallet_weighting",
    "dry_run",
    "synthetic_trade_flag",
    "schema_version",
]


def _run_replay(run_id: str, payload: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    processed_dir = ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    entry_candidates_path = processed_dir / "entry_candidates.json"
    registry_path = ROOT / "data" / "smart_wallets.registry.json"
    run_dir = ROOT / "runs" / run_id

    original_candidates = entry_candidates_path.read_text(encoding="utf-8") if entry_candidates_path.exists() else None
    original_registry = registry_path.read_text(encoding="utf-8") if registry_path.exists() else None
    if run_dir.exists():
        for child in run_dir.iterdir():
            child.unlink()
        run_dir.rmdir()

    try:
        entry_candidates_path.write_text(json.dumps(payload), encoding="utf-8")
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps({"wallets": []}), encoding="utf-8")

        subprocess.run(
            [sys.executable, "scripts/replay_7d.py", "--run-id", run_id, "--dry-run"],
            check=True,
            cwd=ROOT,
        )

        rows = [
            json.loads(line)
            for line in (run_dir / "trade_feature_matrix.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        summary = json.loads((run_dir / "replay_summary.json").read_text(encoding="utf-8"))
        return rows, summary
    finally:
        if original_candidates is None:
            entry_candidates_path.unlink(missing_ok=True)
        else:
            entry_candidates_path.write_text(original_candidates, encoding="utf-8")
        if original_registry is None:
            registry_path.unlink(missing_ok=True)
        else:
            registry_path.write_text(original_registry, encoding="utf-8")


def test_trade_feature_matrix_row_count_matches_trades_count():
    rows, summary = _run_replay(
        "matrix_count_match",
        [
            {"token_address": "tok_a", "pair_address": "pair_a", "decision": "paper_enter"},
            {"token_address": "tok_b", "pair_address": "pair_b", "decision": "paper_enter"},
        ],
    )

    trades_lines = (ROOT / "runs" / "matrix_count_match" / "trades.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == len(trades_lines) == 2
    assert summary["trade_feature_matrix_rows"] == 2


def test_trade_feature_matrix_handles_legacy_payloads_with_null_safe_placeholders():
    rows, _summary = _run_replay(
        "matrix_legacy_payload",
        [
            {
                "token_address": "tok_legacy",
                "pair_address": "pair_legacy",
                "decision": "paper_enter",
                "features": {"age_minutes": 3, "liquidity_usd": 1250.0},
            }
        ],
    )

    row = rows[0]
    assert set(REQUIRED_MATRIX_KEYS).issubset(row.keys())
    assert row["run_id"] == "matrix_legacy_payload"
    assert row["token_address"] == "tok_legacy"
    assert row["pair_address"] == "pair_legacy"
    assert row["symbol"] is None
    assert row["decision"] == "paper_enter"
    assert row["entry_decision"] == "paper_enter"
    assert row["age_minutes"] == 3
    assert row["liquidity_usd"] == 1250.0
    assert row["entry_confidence"] is None
    assert row["recommended_position_pct"] is None
    assert row["bundle_count_first_60s"] is None
    assert row["net_unique_buyers_60s"] is None
    assert row["x_author_velocity_5m"] is None
    assert row["liquidity_shock_recovery_sec"] is None
    assert row["exit_decision"] is None
    assert row["gross_pnl_pct"] is None
    assert row["schema_version"] == "trade_feature_matrix.v1"


def test_trade_feature_matrix_preserves_enriched_payload_fields():
    rows, summary = _run_replay(
        "matrix_enriched_payload",
        [
            {
                "token_address": "tok_enriched",
                "pair_address": "pair_enriched",
                "symbol": "ENR",
                "decision": "paper_enter",
                "regime_decision": "trend",
                "regime_confidence": 0.81,
                "regime_reason_flags": ["fast_momentum"],
                "regime_blockers": [],
                "expected_hold_class": "swing",
                "entry_confidence": 0.84,
                "recommended_position_pct": 0.35,
                "final_score": 91.5,
                "onchain_core": 33.2,
                "early_signal_bonus": 12.0,
                "x_validation_bonus": 5.4,
                "rug_penalty": 2.2,
                "spam_penalty": 1.0,
                "confidence_adjustment": 0.5,
                "wallet_adjustment": {"applied_delta": 1.25},
                "bundle_aggression_bonus": 2.1,
                "organic_multi_cluster_bonus": 1.4,
                "single_cluster_penalty": 0.0,
                "creator_cluster_penalty": 0.0,
                "bundle_sell_heavy_penalty": 0.0,
                "retry_manipulation_penalty": 0.3,
                "features": {
                    "age_sec": 95,
                    "liquidity_usd": 24500.0,
                    "buy_pressure": 0.88,
                    "volume_velocity": 4.2,
                    "holder_growth_5m": 18,
                    "smart_wallet_hits": 4,
                    "net_unique_buyers_60s": 6,
                    "liquidity_refill_ratio_120s": 0.8,
                    "cluster_sell_concentration_120s": 0.62,
                    "smart_wallet_dispersion_score": 0.55,
                    "x_author_velocity_5m": 0.6,
                    "seller_reentry_ratio": 0.25,
                    "liquidity_shock_recovery_sec": 45,
                    "x_validation_delta": 11,
                },
                "x_status": "ok",
                "x_validation_score": 77.0,
                "entry_snapshot": {
                    "bundle_count_first_60s": 5,
                    "bundle_size_value": 15200.0,
                    "unique_wallets_per_bundle_avg": 2.7,
                    "bundle_timing_from_liquidity_add_min": 0.4,
                    "bundle_success_rate": 0.72,
                    "bundle_composition_dominant": "buy-only",
                    "bundle_tip_efficiency": 0.51,
                    "bundle_failure_retry_pattern": 1,
                    "cross_block_bundle_correlation": 0.2,
                    "bundle_wallet_clustering_score": 0.59,
                    "cluster_concentration_ratio": 0.48,
                    "num_unique_clusters_first_60s": 3,
                    "creator_in_cluster_flag": False,
                },
                "wallet_features": {
                    "smart_wallet_score_sum": 14.5,
                    "smart_wallet_tier1_hits": 2,
                    "smart_wallet_tier2_hits": 1,
                    "smart_wallet_unique_count": 3,
                    "smart_wallet_early_entry_hits": 2,
                    "smart_wallet_netflow_bias": 0.35,
                },
            }
        ],
    )

    row = rows[0]
    assert row["config_hash"] == summary["config_hash"]
    assert row["symbol"] == "ENR"
    assert row["regime_decision"] == "trend"
    assert row["regime_confidence"] == 0.81
    assert row["regime_reason_flags"] == ["fast_momentum"]
    assert row["expected_hold_class"] == "swing"
    assert row["entry_confidence"] == 0.84
    assert row["recommended_position_pct"] == 0.35
    assert row["final_score"] == 91.5
    assert row["wallet_adjustment"] == 1.25
    assert row["buy_pressure_entry"] == 0.88
    assert row["x_validation_score_entry"] == 77.0
    assert row["x_validation_delta_entry"] == 11
    assert row["bundle_count_first_60s"] == 5
    assert row["bundle_wallet_clustering_score"] == 0.59
    assert row["smart_wallet_score_sum"] == 14.5
    assert row["smart_wallet_tier1_hits"] == 2
    assert row["smart_wallet_netflow_bias"] == 0.35
    assert row["net_unique_buyers_60s"] == 6
    assert row["smart_wallet_dispersion_score"] == 0.55
    assert row["x_author_velocity_5m"] == 0.6
    assert row["liquidity_shock_recovery_sec"] == 45


def test_trade_feature_matrix_smoke_file_exists_for_replay_run():
    rows, _summary = _run_replay(
        "matrix_smoke_exists",
        [{"token_address": "tok_smoke", "pair_address": "pair_smoke", "decision": "paper_enter"}],
    )

    matrix_path = ROOT / "runs" / "matrix_smoke_exists" / "trade_feature_matrix.jsonl"
    assert matrix_path.exists()
    assert len(rows) == 1
