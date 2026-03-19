import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from analytics.config_suggestions import build_config_suggestions_payload
from config.settings import load_settings
from utils.io import ensure_dir, read_json, write_json


class DummySettings:
    CONFIG_SUGGESTIONS_ENABLED = True
    CONFIG_SUGGESTIONS_MIN_SAMPLE = 5
    CONFIG_SUGGESTIONS_TRAINING_WHEELS_MODE = True
    CONFIG_SUGGESTIONS_CONTRACT_VERSION = "config_suggestions_v1"
    PROCESSED_DATA_DIR = Path("/tmp")
    TRADES_DIR = Path("/tmp")
    SIGNALS_DIR = Path("/tmp")
    POSITIONS_DIR = Path("/tmp")
    ENTRY_TREND_SCORE_MIN = 86
    ENTRY_TREND_MIN_X_SCORE = 65
    UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY = 4.0
    UNIFIED_SCORE_SINGLE_CLUSTER_PENALTY_MAX = 6.0
    UNIFIED_SCORE_RETRY_MANIPULATION_PENALTY_MAX = 4.0
    UNIFIED_SCORE_BUNDLE_SELL_HEAVY_PENALTY_MAX = 5.0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_config_suggestions_gracefully_handle_missing_matrix_and_ml():
    payload = build_config_suggestions_payload(
        settings=DummySettings(),
        summary={"as_of": "2026-03-19T00:00:00Z", "total_positions_closed": 2, "matrix_analysis_available": False},
        recommendations_payload={"recommendations": []},
        matrix_rows=[],
    )

    assert payload["inputs"]["matrix_available"] is False
    assert payload["inputs"]["ml_summary_available"] is False
    assert "matrix_artifact_missing_or_unusable" in payload["warnings"]
    assert "ml_artifacts_missing" in payload["warnings"]
    assert any(item["suggestion_type"] == "collect_more_data_first" for item in payload["suggestions"])


def test_config_suggestions_low_sample_evidence_stays_monitor_only():
    payload = build_config_suggestions_payload(
        settings=DummySettings(),
        summary={
            "as_of": "2026-03-19T00:00:00Z",
            "total_positions_closed": 4,
            "matrix_analysis_available": True,
            "pattern_expectancy_slices": {
                "creator_in_cluster_flag:true": {"count": 4, "avg_net_pnl_pct": -5.0},
                "creator_in_cluster_flag:false": {"count": 4, "avg_net_pnl_pct": 1.0},
            },
        },
        recommendations_payload={"recommendations": []},
        matrix_rows=[{"position_id": "p1"}],
    )

    creator = next(item for item in payload["suggestions"] if item["parameter"] == "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY")
    assert creator["suggestion_type"] == "monitor_only"
    assert creator["suggested_value"] is None
    assert "insufficient_closed_positions_for_numeric_suggestions" in payload["warnings"]


def test_config_suggestions_emit_creator_cluster_penalty_change_on_strong_evidence():
    payload = build_config_suggestions_payload(
        settings=DummySettings(),
        summary={
            "as_of": "2026-03-19T00:00:00Z",
            "total_positions_closed": 12,
            "matrix_analysis_available": True,
            "pattern_expectancy_slices": {
                "creator_in_cluster_flag:true": {"count": 7, "avg_net_pnl_pct": -6.5},
                "creator_in_cluster_flag:false": {"count": 5, "avg_net_pnl_pct": 3.0},
            },
        },
        recommendations_payload={
            "recommendations": [
                {
                    "target": "creator-linked clusters",
                    "suggested_action": "tighten_or_penalize_creator_cluster_exposure",
                    "confidence": 0.74,
                }
            ]
        },
        matrix_rows=[{"position_id": f"p{i}"} for i in range(12)],
    )

    creator = next(item for item in payload["suggestions"] if item["parameter"] == "UNIFIED_SCORE_CREATOR_CLUSTER_PENALTY")
    assert creator["suggestion_type"] == "increase_penalty_cap"
    assert creator["suggested_value"] == 4.5
    assert creator["apply_mode"] == "manual_only"
    assert creator["confidence"] >= 0.6


def test_config_suggestions_emit_scalp_missed_trend_gate_change():
    payload = build_config_suggestions_payload(
        settings=DummySettings(),
        summary={
            "as_of": "2026-03-19T00:00:00Z",
            "total_positions_closed": 10,
            "matrix_analysis_available": True,
            "scalp_missed_trend_summary": {
                "count": 6,
                "avg_mfe_capture_gap_pct": 14.0,
                "supporting_evidence_count": 6,
            },
            "trend_failure_summary": {"count": 1, "avg_net_pnl_pct": -1.0},
        },
        recommendations_payload={
            "recommendations": [
                {
                    "target": "SCALP->TREND upgrade path",
                    "suggested_action": "allow_more_trend_follow_through_when_continuation_evidence_is_present",
                    "confidence": 0.69,
                }
            ]
        },
        matrix_rows=[{"position_id": f"p{i}"} for i in range(10)],
    )

    trend_gate = next(item for item in payload["suggestions"] if item["parameter"] == "ENTRY_TREND_SCORE_MIN")
    assert trend_gate["suggestion_type"] == "loosen_threshold"
    assert trend_gate["suggested_value"] == 85
    assert trend_gate["direction"] == "decrease"


def test_config_suggestions_emit_trend_failed_fast_blocker_change():
    payload = build_config_suggestions_payload(
        settings=DummySettings(),
        summary={
            "as_of": "2026-03-19T00:00:00Z",
            "total_positions_closed": 11,
            "matrix_analysis_available": True,
            "trend_failure_summary": {"count": 6, "avg_net_pnl_pct": -7.0},
            "regime_confusion_summary": {
                "regime_confidence_buckets": {
                    "regime_confidence:gte_0.7": {"count": 5, "avg_net_pnl_pct": 4.0},
                    "regime_confidence:lt_0.7": {"count": 5, "avg_net_pnl_pct": -1.5},
                }
            },
        },
        recommendations_payload={
            "recommendations": [
                {
                    "target": "TREND promotion guard",
                    "suggested_action": "raise_trend_confidence_and_breakdown_filters",
                    "confidence": 0.71,
                }
            ]
        },
        matrix_rows=[{"position_id": f"p{i}"} for i in range(11)],
    )

    blocker = next(item for item in payload["suggestions"] if item["parameter"] == "ENTRY_TREND_MIN_X_SCORE")
    assert blocker["suggestion_type"] == "tighten_threshold"
    assert blocker["suggested_value"] == 66
    assert blocker["direction"] == "increase"


def test_config_suggestions_schema_and_no_config_write_regression(tmp_path):
    trades_dir = ensure_dir(tmp_path / "trades")
    signals_dir = ensure_dir(tmp_path / "signals")
    positions_dir = ensure_dir(tmp_path / "positions")
    processed_dir = ensure_dir(tmp_path / "processed")
    config_dir = ensure_dir(tmp_path / "config")
    config_file = config_dir / "replay.default.yaml"
    config_file.write_text("UNCHANGED\n", encoding="utf-8")

    _write_jsonl(
        trades_dir / "trades.jsonl",
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
    _write_jsonl(signals_dir / "signals.jsonl", [{"signal": 1}])
    write_json(positions_dir / "positions.json", [{"position_id": "p1", "status": "closed"}])
    write_json(processed_dir / "portfolio_state.json", {"starting_equity_sol": 0.10, "unrealized_pnl_sol": 0.0, "equity_sol": 0.099})

    os.environ["TRADES_DIR"] = str(trades_dir)
    os.environ["SIGNALS_DIR"] = str(signals_dir)
    os.environ["POSITIONS_DIR"] = str(positions_dir)
    os.environ["PROCESSED_DATA_DIR"] = str(processed_dir)
    os.environ["POST_RUN_MIN_TRADES_FOR_CORRELATION"] = "1"
    os.environ["POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON"] = "1"
    os.environ["POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION"] = "1"
    os.environ["CONFIG_SUGGESTIONS_MIN_SAMPLE"] = "1"
    os.environ["POST_RUN_OUTLIER_CLIP_PCT"] = "0"

    settings = load_settings()
    result = run_post_run_analysis(settings)

    suggestions = read_json(Path(result["config_suggestions_path"]))
    assert suggestions["training_wheels_mode"] is True
    assert isinstance(suggestions["warnings"], list)
    assert Path(result["config_suggestions_path"]).exists()
    assert config_file.read_text(encoding="utf-8") == "UNCHANGED\n"

    for item in suggestions["suggestions"]:
        assert "parameter" in item
        assert "confidence" in item
        assert "reason" in item
        assert "evidence" in item
        assert item["apply_mode"] == "manual_only"
