from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from analytics.analyzer_matrix import compute_matrix_analysis, merge_closed_positions_with_matrix
from config.settings import load_settings
from src.replay.calibration_metrics import (
    PriceObservation,
    compute_mae_pct_240s,
    compute_mfe_pct_240s,
    compute_time_to_first_profit_sec,
    compute_trend_survival,
    derive_outcome_metrics,
)
from utils.io import ensure_dir, read_json, write_json


class DummySettings:
    POST_RUN_MIN_TRADES_FOR_CORRELATION = 1
    POST_RUN_OUTLIER_CLIP_PCT = 0.0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_deterministic_trajectory_metrics_are_correct():
    observations = [
        PriceObservation(0, 1.0),
        PriceObservation(15, 0.98),
        PriceObservation(45, 1.02),
        PriceObservation(120, 1.15),
        PriceObservation(240, 1.11),
        PriceObservation(900, 1.07),
        PriceObservation(3600, 0.95),
    ]

    assert compute_time_to_first_profit_sec(1.0, observations) == 45.0
    assert compute_mfe_pct_240s(1.0, observations) == pytest.approx(15.0)
    assert compute_mae_pct_240s(1.0, observations) == pytest.approx(-2.0)
    assert compute_trend_survival(1.0, observations, window_sec=15 * 60) == pytest.approx(0.95)
    assert compute_trend_survival(1.0, observations, window_sec=60 * 60) == pytest.approx(0.2375)


def test_derive_outcome_metrics_returns_none_without_honest_path_evidence():
    metrics = derive_outcome_metrics({"entry_price": 1.0})

    assert metrics == {
        "time_to_first_profit_sec": None,
        "mfe_pct_240s": None,
        "mae_pct_240s": None,
        "trend_survival_15m": None,
        "trend_survival_60m": None,
    }


def test_matrix_analysis_adds_calibration_only_summary_sections():
    rows = [
        {
            "position_id": "p_scalp",
            "regime_decision": "SCALP",
            "net_pnl_pct": 4.0,
            "time_to_first_profit_sec": 20.0,
            "mfe_pct_240s": 12.0,
            "mae_pct_240s": -3.0,
            "trend_survival_15m": 0.8,
            "trend_survival_60m": 0.5,
        },
        {
            "position_id": "p_trend",
            "regime_decision": "TREND",
            "net_pnl_pct": -2.0,
            "time_to_first_profit_sec": 90.0,
            "mfe_pct_240s": 5.0,
            "mae_pct_240s": -9.0,
            "trend_survival_15m": 0.3,
            "trend_survival_60m": 0.1,
        },
    ]

    analysis = compute_matrix_analysis(rows, DummySettings())

    assert analysis["time_to_first_profit_summary"]["overall"]["count"] == 2
    assert analysis["mfe_mae_summary"]["mfe_pct_240s"]["max"] == pytest.approx(12.0)
    assert analysis["trend_survival_summary"]["trend_survival_60m"]["avg"] == pytest.approx(0.3)
    assert analysis["scalp_vs_trend_outcome_summary"]["SCALP"]["trend_survival_15m"]["avg"] == pytest.approx(0.8)


def test_merge_closed_positions_with_matrix_preserves_reconstructed_calibration_metrics_when_matrix_is_null():
    closed_positions = [
        {
            "position_id": "p1",
            "net_pnl_pct": 1.0,
            "time_to_first_profit_sec": 30.0,
            "mfe_pct_240s": 9.0,
            "mae_pct_240s": -2.0,
        }
    ]
    matrix_rows = [{"position_id": "p1", "regime_decision": "SCALP", "time_to_first_profit_sec": None}]

    merged = merge_closed_positions_with_matrix(closed_positions, matrix_rows)

    assert merged[0]["regime_decision"] == "SCALP"
    assert merged[0]["time_to_first_profit_sec"] == 30.0
    assert merged[0]["mfe_pct_240s"] == 9.0


def test_run_post_run_analysis_reports_calibration_sections_when_metrics_exist(tmp_path):
    run_dir = ensure_dir(tmp_path / "runs" / "analyzer_calibration")
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
                "price": 1.0,
                "price_path": [
                    {"offset_sec": 0, "price": 1.0},
                    {"offset_sec": 20, "price": 1.03},
                    {"offset_sec": 240, "price": 1.10},
                    {"offset_sec": 900, "price": 1.02},
                    {"offset_sec": 3600, "price": 0.97},
                ],
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
                "gross_pnl_sol": 0.0012,
                "slippage_bps": 40,
                "priority_fee_sol": 0.00002,
            },
        ],
    )
    _write_jsonl(run_dir / "signals.jsonl", [{"signal": 1}])
    write_json(run_dir / "positions.json", [{"position_id": "p1", "status": "closed"}])
    write_json(run_dir / "portfolio_state.json", {"starting_equity_sol": 0.10, "unrealized_pnl_sol": 0.0, "equity_sol": 0.101})
    _write_jsonl(run_dir / "trade_feature_matrix.jsonl", [{"position_id": "p1", "regime_decision": "SCALP", "time_to_first_profit_sec": None}])

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
    report = Path(result["report_path"]).read_text(encoding="utf-8")

    assert summary["time_to_first_profit_summary"]["overall"]["count"] == 1
    assert summary["mfe_mae_summary"]["mfe_pct_240s"]["max"] == pytest.approx(10.0)
    assert "calibration-only outcome summaries" in report
    assert "SCALP.time_to_first_profit_sec" in report
