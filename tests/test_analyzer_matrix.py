import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from analytics.analyzer_matrix import (
    compute_matrix_analysis,
    compute_regime_confusion_slices,
    compute_scalp_missed_trend_slices,
    merge_closed_positions_with_matrix,
)
from config.settings import load_settings
from utils.io import ensure_dir, read_json, write_json


class DummySettings:
    POST_RUN_MIN_TRADES_FOR_CORRELATION = 3
    POST_RUN_OUTLIER_CLIP_PCT = 0.0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_matrix_correlations_and_creator_cluster_slice():
    rows = [
        {
            "position_id": f"p{i}",
            "net_pnl_pct": pnl,
            "creator_cluster_penalty": penalty,
            "cluster_concentration_ratio": concentration,
            "creator_in_cluster_flag": creator,
        }
        for i, (pnl, penalty, concentration, creator) in enumerate(
            [
                (12.0, 0.1, 0.2, False),
                (8.0, 0.2, 0.3, False),
                (-6.0, 0.8, 0.7, True),
                (-9.0, 0.9, 0.8, True),
            ],
            start=1,
        )
    ]

    analysis = compute_matrix_analysis(rows, DummySettings())

    penalty_corr = next(row for row in analysis["bundle_cluster_correlations"] if row["metric"] == "creator_cluster_penalty")
    assert penalty_corr["status"] == "ok"
    assert penalty_corr["direction"] == "negative"
    assert analysis["pattern_expectancy_slices"]["creator_in_cluster_flag:true"]["avg_net_pnl_pct"] < 0
    assert analysis["pattern_expectancy_slices"]["cluster_concentration_ratio:gte_0.6"]["avg_net_pnl_pct"] < 0


def test_trend_failed_fast_slice_detects_negative_short_trend_trades():
    rows = [
        {"regime_decision": "TREND", "hold_sec": 120, "net_pnl_pct": -8.0, "exit_reason_final": "breakdown", "regime_confidence": 0.86},
        {"regime_decision": "TREND", "hold_sec": 180, "net_pnl_pct": -4.0, "exit_reason_final": "risk", "regime_confidence": 0.74},
        {"regime_decision": "TREND", "hold_sec": 900, "net_pnl_pct": 15.0, "exit_reason_final": "trend_take_profit", "regime_confidence": 0.83},
    ]

    summary = compute_regime_confusion_slices(rows)

    assert summary["trend_promoted_failed_fast"]["count"] == 2
    assert summary["trend_promoted_failed_fast"]["avg_net_pnl_pct"] < 0


def test_scalp_missed_trend_slice_requires_mfe_gap_and_supporting_evidence():
    rows = [
        {
            "regime_decision": "SCALP",
            "net_pnl_pct": 2.0,
            "mfe_pct": 18.0,
            "hold_sec": 140,
            "bundle_aggression_bonus": 0.3,
            "organic_multi_cluster_bonus": 0.4,
            "single_cluster_penalty": 0.1,
            "creator_in_cluster_flag": False,
        },
        {
            "regime_decision": "SCALP",
            "net_pnl_pct": 1.0,
            "mfe_pct": 5.0,
            "hold_sec": 120,
            "bundle_aggression_bonus": 0.1,
        },
    ]

    summary = compute_scalp_missed_trend_slices(rows)

    assert summary["count"] == 1
    assert summary["avg_mfe_capture_gap_pct"] == 16.0


def test_run_post_run_analysis_with_matrix_adds_matrix_sections(tmp_path):
    run_dir = ensure_dir(tmp_path / "runs" / "analyzer_matrix_smoke")
    _write_jsonl(
        run_dir / "trades.jsonl",
        [
            {
                "position_id": "p1",
                "token_address": "So111",
                "side": "buy",
                "status": "filled",
                "timestamp": "2026-03-15T12:30:00Z",
                "regime": "SCALP",
                "size_sol": 0.01,
                "entry_snapshot": {"bundle_cluster_score": 0.5, "first30s_buy_ratio": 0.6, "x_validation_score": 70},
            },
            {
                "position_id": "p1",
                "token_address": "So111",
                "side": "sell",
                "status": "filled",
                "timestamp": "2026-03-15T12:31:00Z",
                "exit_reason": "scalp_stop_loss",
                "net_pnl_sol": -0.001,
                "gross_pnl_sol": -0.0008,
                "slippage_bps": 190,
                "priority_fee_sol": 0.00002,
            },
        ],
    )
    _write_jsonl(run_dir / "signals.jsonl", [{"signal": 1}])
    write_json(run_dir / "positions.json", [{"position_id": "p1", "status": "closed"}])
    write_json(run_dir / "portfolio_state.json", {"starting_equity_sol": 0.10, "unrealized_pnl_sol": 0.0, "equity_sol": 0.099})
    _write_jsonl(
        run_dir / "trade_feature_matrix.jsonl",
        [
            {
                "position_id": "p1",
                "regime_decision": "TREND",
                "regime_confidence": 0.82,
                "creator_cluster_penalty": 0.8,
                "cluster_concentration_ratio": 0.74,
                "bundle_sell_heavy_penalty": 0.9,
                "retry_manipulation_penalty": 0.7,
                "bundle_composition_dominant": "sell_only",
                "creator_in_cluster_flag": True,
                "hold_sec": 60,
                "net_pnl_pct": -10.0,
                "mfe_pct": 1.0,
                "exit_reason_final": "breakdown",
            }
        ],
    )

    os.environ["TRADES_DIR"] = str(run_dir)
    os.environ["SIGNALS_DIR"] = str(run_dir)
    os.environ["POSITIONS_DIR"] = str(run_dir)
    os.environ["PROCESSED_DATA_DIR"] = str(run_dir)
    os.environ["POST_RUN_MIN_TRADES_FOR_CORRELATION"] = "1"
    os.environ["POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON"] = "1"
    os.environ["POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION"] = "1"
    os.environ["POST_RUN_OUTLIER_CLIP_PCT"] = "0"

    settings = load_settings()
    result = run_post_run_analysis(settings)
    summary = read_json(Path(result["summary_path"]))
    recommendations = read_json(Path(result["recommendations_path"]))
    report = Path(result["report_path"]).read_text(encoding="utf-8")

    assert summary["matrix_analysis_available"] is True
    assert summary["matrix_row_count"] == 1
    assert summary["trade_feature_matrix_path"].endswith("trade_feature_matrix.jsonl")
    assert summary["analyzer_slice_source"] == "trade_feature_matrix"
    assert "creator_in_cluster_flag:true" in summary["pattern_expectancy_slices"]
    assert summary["trend_failure_summary"]["count"] == 1
    assert any(rec["type"].startswith("matrix_") for rec in recommendations["recommendations"])
    assert "## bundle / cluster feature insights" in report
    assert "## regime misclassification insights" in report


def test_merge_closed_positions_with_matrix_preserves_legacy_positions_and_skips_unusable_rows():
    closed_positions = [{"position_id": "p1", "net_pnl_pct": -5.0, "hold_sec": 60}]
    matrix_rows = [
        {"position_id": "p1", "regime_decision": "TREND", "creator_cluster_penalty": 0.8},
        {"position_id": "missing", "regime_decision": "SCALP"},
    ]

    merged = merge_closed_positions_with_matrix(closed_positions, matrix_rows)

    assert len(merged) == 1
    assert merged[0]["regime_decision"] == "TREND"
    assert merged[0]["net_pnl_pct"] == -5.0


def test_analyzer_prefers_canonical_matrix_jsonl_path(tmp_path):
    from analytics.analyzer_matrix import resolve_trade_feature_matrix_path

    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trade_feature_matrix.json").write_text("[]", encoding="utf-8")
    (run_dir / "trade_feature_matrix.jsonl").write_text("{}\n", encoding="utf-8")

    class _Settings:
        TRADES_DIR = run_dir
        SIGNALS_DIR = run_dir
        POSITIONS_DIR = run_dir
        PROCESSED_DATA_DIR = run_dir

    resolved = resolve_trade_feature_matrix_path(_Settings())
    assert resolved is not None
    assert resolved.name == "trade_feature_matrix.jsonl"

def test_resolve_trade_feature_matrix_prefers_canonical_jsonl_over_legacy_json(tmp_path):
    from types import SimpleNamespace
    from analytics.analyzer_matrix import resolve_trade_feature_matrix_path

    (tmp_path / "trade_feature_matrix.jsonl").write_text(
        '{"schema_version":"trade_feature_matrix.v1"}\n',
        encoding="utf-8",
    )
    (tmp_path / "trade_feature_matrix.json").write_text("[]", encoding="utf-8")

    settings = SimpleNamespace(
        TRADES_DIR=tmp_path,
        SIGNALS_DIR=tmp_path,
        POSITIONS_DIR=tmp_path,
        PROCESSED_DATA_DIR=tmp_path,
    )
    path = resolve_trade_feature_matrix_path(settings)
    assert path is not None
    assert path.name == "trade_feature_matrix.jsonl"
