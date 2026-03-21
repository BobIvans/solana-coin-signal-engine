import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from analytics.analyzer_slices import compute_analyzer_slices
from config.settings import load_settings
from utils.io import ensure_dir, read_json, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _rich_rows() -> list[dict]:
    rows = []
    dataset = [
        ("t1", "TREND", -8.0, 120, 0.82, True, 0.82, 1, 0.75, 0.80, 0.22, 260, "degraded", 0.25, True, "cluster_dump", 0),
        ("t2", "TREND", -5.0, 180, 0.78, True, 0.70, 1, 0.68, 0.72, 0.28, 220, "degraded", 0.30, True, "creator_cluster_exit", 0),
        ("t3", "TREND", -3.0, 150, 0.74, True, 0.66, 1, 0.65, 0.70, 0.27, 210, "degraded", 0.40, True, "bundle_failure_spike", 1),
        ("t4", "TREND", 12.0, 1200, 0.88, False, 0.25, 3, 0.20, 0.30, 0.72, 80, "healthy", 1.20, False, "trend_take_profit", 1),
        ("t5", "TREND", 9.0, 900, 0.84, False, 0.30, 2, 0.25, 0.35, 0.74, 90, "healthy", 1.10, False, "trend_take_profit", 0),
        ("t6", "SCALP", 2.0, 140, 0.61, False, 0.22, 3, 0.18, 0.25, 0.70, 75, "healthy", 1.05, False, "scalp_take_profit", 0),
        ("t7", "SCALP", 1.5, 110, 0.58, False, 0.18, 2, 0.22, 0.30, 0.68, 70, "healthy", 1.15, False, "scalp_take_profit", 0),
        ("t8", "SCALP", 1.2, 130, 0.55, False, 0.20, 2, 0.28, 0.35, 0.64, 85, "healthy", 1.02, False, "scalp_take_profit", 0),
        ("t9", "SCALP", 3.0, 180, 0.66, False, 0.24, 3, 0.20, 0.20, 0.76, 60, "healthy", 1.30, False, "scalp_take_profit", 1),
        ("t10", "SCALP", 2.5, 160, 0.64, False, 0.26, 2, 0.22, 0.22, 0.78, 55, "healthy", 1.25, False, "scalp_take_profit", 0),
        ("t11", "SCALP", 1.0, 100, 0.59, False, 0.21, 2, 0.18, 0.24, 0.66, 65, "degraded", 0.35, False, "scalp_take_profit", 0),
        ("t12", "SCALP", -1.0, 90, 0.53, False, 0.24, 2, 0.20, 0.28, 0.62, 95, "degraded", 0.32, False, "scalp_stop_loss", 0),
    ]
    for (
        position_id,
        regime,
        pnl,
        hold_sec,
        regime_confidence,
        creator_flag,
        cluster_concentration_ratio,
        num_clusters,
        seller_reentry_ratio,
        cluster_sell_concentration,
        smart_wallet_dispersion,
        shock_recovery,
        x_status,
        size_sol,
        retry_flag,
        exit_reason,
        partial_exit_count,
    ) in dataset:
        rows.append(
            {
                "position_id": position_id,
                "regime_decision": regime,
                "net_pnl_pct": pnl,
                "hold_sec": hold_sec,
                "regime_confidence": regime_confidence,
                "mfe_pct": pnl + (12.0 if regime == "SCALP" else 2.0),
                "trend_survival_15m": 0.8 if regime == "SCALP" and pnl > 0 else 0.2,
                "trend_survival_60m": 0.6 if regime == "SCALP" and pnl > 0 else 0.1,
                "liquidity_refill_ratio_120s": 1.15 if pnl > 0 else 0.55,
                "seller_reentry_ratio": seller_reentry_ratio,
                "liquidity_shock_recovery_sec": shock_recovery,
                "cluster_sell_concentration_120s": cluster_sell_concentration,
                "net_unique_buyers_60s": 20 if pnl > 0 else 8,
                "smart_wallet_dispersion_score": smart_wallet_dispersion,
                "x_author_velocity_5m": 0.72 if pnl > 0 else 0.18,
                "creator_in_cluster_flag": creator_flag,
                "creator_cluster_penalty": 0.85 if creator_flag else 0.10,
                "single_cluster_penalty": 0.75 if num_clusters == 1 else 0.10,
                "cluster_concentration_ratio": cluster_concentration_ratio,
                "num_unique_clusters_first_60s": num_clusters,
                "organic_multi_cluster_bonus": 0.55 if num_clusters >= 2 else 0.0,
                "bundle_sell_heavy_penalty": 0.82 if pnl < 0 else 0.12,
                "retry_manipulation_penalty": 0.78 if retry_flag else 0.08,
                "bundle_failure_retry_pattern": "retry_heavy" if retry_flag else "clean",
                "bundle_composition_dominant": "sell_only" if pnl < 0 else "mixed",
                "cross_block_bundle_correlation": 0.81 if pnl < 0 else 0.20,
                "bundle_tip_efficiency": 0.22 if pnl < 0 else 0.68,
                "x_status": x_status,
                "size_sol": size_sol,
                "exit_reason_final": exit_reason,
                "partial_exit_count": partial_exit_count,
                "evidence_quality_score": 0.82 if pnl > 0 else 0.38,
                "sizing_confidence": 0.78 if pnl > 0 else 0.36,
                "evidence_conflict_flag": position_id in {"t1", "t12"},
                "partial_evidence_flag": position_id in {"t1", "t11"},
                "continuation_status": "partial" if position_id in {"t2", "t12"} else "ok",
                "bundle_evidence_status": "partial" if position_id == "t3" else "ok",
                "cluster_evidence_status": "partial" if position_id == "t1" else "ok",
                "linkage_status": "partial" if position_id == "t2" else "ok",
                "runtime_signal_status": "partial" if position_id == "t3" else "ok",
                "tx_batch_status": "partial" if position_id == "t12" else "ok",
                "linkage_risk_score": 0.72 if pnl < 0 else 0.18,
                "linkage_confidence": "low" if pnl < 0 else "high",
                "sizing_reason_codes": ["low_confidence"] if position_id in {"t1", "t2", "t3", "t11", "t12"} else ["supported"],
            }
        )
    return rows


def test_compute_analyzer_slices_rich_groups():
    payload = compute_analyzer_slices(_rich_rows(), min_sample=2, run_id="fixture-run", source="fixture")

    regime = payload["slice_groups"]["regime"]
    assert regime["trend_promoted_but_failed_fast"]["sample_size"] == 3
    assert regime["scalp_should_have_been_trend"]["sample_size"] >= 4
    assert regime["regime_confidence_buckets"]["status"] == "observed"

    cluster = payload["slice_groups"]["cluster_bundle"]
    assert cluster["creator_linked_underperformance"]["expectancy"] < 0
    assert cluster["multi_cluster_outperformance"]["expectancy"] > 0

    continuation = payload["slice_groups"]["continuation"]
    assert continuation["failed_liquidity_refill_underperformance"]["expectancy"] < 0
    assert continuation["weak_reentry_underperformance"]["sample_size"] >= 1
    assert continuation["shock_not_recovered_underperformance"]["sample_size"] >= 1
    assert continuation["shock_not_recovered_underperformance"]["expectancy"] < 0
    assert continuation["organic_buyer_flow_positive_slices"]["expectancy"] > 0

    degraded = payload["slice_groups"]["degraded_x"]
    assert degraded["degraded_x_vs_healthy_x"]["degraded_sample_size"] >= 1
    assert degraded["degraded_x_salvage_cases"]["sample_size"] >= 1

    evidence_quality = payload["slice_groups"]["evidence_quality"]
    assert payload["evidence_quality_slices"] == evidence_quality
    assert evidence_quality["partial_evidence_trades"]["sample_size"] >= 1
    assert evidence_quality["low_confidence_evidence_trades"]["sample_size"] >= 1
    assert evidence_quality["evidence_conflict_trades"]["sample_size"] >= 1
    assert evidence_quality["degraded_x_trades"]["sample_size"] >= 1
    assert evidence_quality["degraded_x_salvage_cases"]["sample_size"] >= 1
    assert evidence_quality["linkage_risk_underperformance"]["expectancy"] < 0

    exit_failure = payload["slice_groups"]["exit_failure"]
    assert exit_failure["creator_cluster_exit_risk_performance"]["sample_size"] >= 2
    assert payload["recommendation_inputs"]["manual_only"] is True
    assert payload["recommendation_inputs"]["actionable_slices"]


def test_evidence_quality_slices_bucket_rows_deterministically():
    rows = [
        {
            "position_id": "partial-flag",
            "net_pnl_pct": -4.0,
            "partial_evidence_flag": True,
            "evidence_quality_score": 0.35,
            "sizing_confidence": 0.34,
            "evidence_conflict_flag": True,
            "x_status": "degraded",
            "linkage_risk_score": 0.72,
        },
        {
            "position_id": "partial-status",
            "net_pnl_pct": -2.0,
            "continuation_status": "partial",
            "evidence_quality_score": 0.62,
            "sizing_confidence": 0.60,
            "x_status": "ok",
            "linkage_risk_score": 0.20,
        },
        {
            "position_id": "low-confidence-only",
            "net_pnl_pct": 1.0,
            "evidence_quality_score": 0.41,
            "sizing_confidence": 0.70,
            "x_status": "ok",
            "linkage_risk_score": 0.20,
        },
        {
            "position_id": "degraded-salvage",
            "net_pnl_pct": 3.5,
            "evidence_quality_score": 0.66,
            "sizing_confidence": 0.64,
            "x_status": "degraded",
            "linkage_risk_score": 0.18,
        },
        {
            "position_id": "linkage-risk-underperform",
            "net_pnl_pct": -1.5,
            "evidence_quality_score": 0.70,
            "sizing_confidence": 0.68,
            "x_status": "ok",
            "linkage_risk_score": 0.61,
        },
        {
            "position_id": "healthy",
            "net_pnl_pct": 4.0,
            "evidence_quality_score": 0.88,
            "sizing_confidence": 0.82,
            "x_status": "ok",
            "linkage_risk_score": 0.12,
        },
    ]

    payload = compute_analyzer_slices(rows, min_sample=1, run_id="evidence-quality", source="fixture")
    group = payload["slice_groups"]["evidence_quality"]

    assert set(payload["evidence_quality_slices"]) >= {
        "partial_evidence_trades",
        "low_confidence_evidence_trades",
        "evidence_conflict_trades",
        "degraded_x_trades",
        "degraded_x_salvage_cases",
        "linkage_risk_underperformance",
    }
    assert group["partial_evidence_trades"]["sample_size"] == 2
    assert group["low_confidence_evidence_trades"]["sample_size"] == 2
    assert group["evidence_conflict_trades"]["sample_size"] == 1
    assert group["degraded_x_trades"]["sample_size"] == 2
    assert group["degraded_x_salvage_cases"]["sample_size"] == 1
    assert group["linkage_risk_underperformance"]["sample_size"] == 2
    assert group["healthy_evidence_trades"]["sample_size"] == 1
    assert "degraded-X plus positive realized net_pnl_pct" in group["degraded_x_salvage_cases"]["interpretation"]


def test_run_post_run_analysis_writes_analyzer_slice_outputs(tmp_path):
    run_dir = ensure_dir(tmp_path / "runs" / "analyzer_slices")
    trades = [
        {
            "position_id": "p1",
            "token_address": "So111",
            "side": "buy",
            "status": "filled",
            "timestamp": "2026-03-15T12:30:00Z",
            "regime": "SCALP",
            "size_sol": 0.25,
            "entry_snapshot": {"bundle_cluster_score": 0.5, "first30s_buy_ratio": 0.6, "x_validation_score": 70},
        },
        {
            "position_id": "p1",
            "token_address": "So111",
            "side": "sell",
            "status": "filled",
            "timestamp": "2026-03-15T12:31:00Z",
            "exit_reason": "scalp_take_profit",
            "net_pnl_sol": 0.001,
            "gross_pnl_sol": 0.0011,
        },
    ]
    signals = [{"signal": 1}]
    positions = [{"position_id": "p1", "status": "closed"}]
    portfolio_state = {"starting_equity_sol": 0.10, "unrealized_pnl_sol": 0.0, "equity_sol": 0.101}
    matrix_rows = _rich_rows()

    _write_jsonl(run_dir / "trades.jsonl", trades)
    _write_jsonl(run_dir / "signals.jsonl", signals)
    _write_jsonl(run_dir / "trade_feature_matrix.jsonl", matrix_rows)
    write_json(run_dir / "positions.json", positions)
    write_json(run_dir / "portfolio_state.json", portfolio_state)

    os.environ["TRADES_DIR"] = str(run_dir)
    os.environ["SIGNALS_DIR"] = str(run_dir)
    os.environ["POSITIONS_DIR"] = str(run_dir)
    os.environ["PROCESSED_DATA_DIR"] = str(run_dir)
    os.environ["POST_RUN_MIN_TRADES_FOR_CORRELATION"] = "1"
    os.environ["POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON"] = "2"
    os.environ["POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION"] = "2"
    os.environ["POST_RUN_OUTLIER_CLIP_PCT"] = "0"

    settings = load_settings()
    result = run_post_run_analysis(settings)

    analyzer_slices_path = Path(result["analyzer_slices_path"])
    assert analyzer_slices_path.exists()
    payload = read_json(analyzer_slices_path)
    assert payload["slice_groups"]["cluster_bundle"]["creator_linked_underperformance"]["sample_size"] >= 2
    assert payload["slice_groups"]["evidence_quality"]["degraded_x_trades"]["sample_size"] >= 1
    assert payload["evidence_quality_slices"]["linkage_risk_underperformance"]["sample_size"] >= 1

    recommendations = read_json(Path(result["recommendations_path"]))
    assert recommendations["analyzer_slices"]["metadata"]["contract_version"] == "analyzer_slices.v1"
    assert any(rec["type"] == "slice_manual_review" for rec in recommendations["recommendations"])

    summary = read_json(Path(result["summary_path"]))
    assert summary["analyzer_slice_source"] == "trade_feature_matrix"
    assert summary["missing_evidence_quality_slices"] == []

    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "## regime diagnostics" in report
    assert "## continuation diagnostics" in report
    assert "## degraded X diagnostics" in report
    assert "## evidence quality diagnostics" in report
