import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from config.settings import load_settings
from utils.io import ensure_dir, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_run_post_run_analysis_outputs(tmp_path):
    trades_dir = ensure_dir(tmp_path / "trades")
    signals_dir = ensure_dir(tmp_path / "signals")
    positions_dir = ensure_dir(tmp_path / "positions")
    processed_dir = ensure_dir(tmp_path / "processed")

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
                "x_status": "degraded",
                "partial_evidence_flag": True,
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
    write_json(
        processed_dir / "portfolio_state.json",
        {
            "starting_equity_sol": 0.10,
            "unrealized_pnl_sol": 0.0,
            "equity_sol": 0.099,
        },
    )
    write_json(
        processed_dir / "runtime_health.json",
        {
            "runtime_current_state_live_count": 2,
            "runtime_current_state_fallback_count": 1,
            "runtime_current_state_stale_count": 1,
            "tx_window_partial_count": 1,
            "tx_window_truncated_count": 0,
            "unresolved_replay_row_count": 0,
        },
    )

    os.environ["TRADES_DIR"] = str(trades_dir)
    os.environ["SIGNALS_DIR"] = str(signals_dir)
    os.environ["POSITIONS_DIR"] = str(positions_dir)
    os.environ["PROCESSED_DATA_DIR"] = str(processed_dir)

    settings = load_settings()
    result = run_post_run_analysis(settings)
    assert Path(result["summary_path"]).exists()
    assert Path(result["recommendations_path"]).exists()
    assert Path(result["config_suggestions_path"]).exists()
    assert Path(result["report_path"]).exists()

    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["matrix_analysis_available"] is False
    assert "matrix_input_missing" in summary["warnings"]
    assert summary["health_summary"]["runtime_stale_state_share"] == 0.25
    assert summary["health_summary"]["partial_evidence_trade_share"] == 0.5
