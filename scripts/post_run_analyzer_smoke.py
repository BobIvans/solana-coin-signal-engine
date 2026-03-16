"""Smoke runner for post-run analyzer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from config.settings import load_settings
from utils.io import ensure_dir, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _prepare_fixture(root: Path) -> None:
    trades_dir = ensure_dir(root / "trades")
    signals_dir = ensure_dir(root / "signals")
    positions_dir = ensure_dir(root / "positions")
    processed_dir = ensure_dir(root / "processed")

    trades = [
        {
            "position_id": "pos_1",
            "token_address": "So111",
            "side": "buy",
            "status": "filled",
            "timestamp": "2026-03-15T12:30:42Z",
            "regime": "SCALP",
            "size_sol": 0.01,
            "entry_confidence": 0.66,
            "final_score": 87,
            "rug_score": 0.1,
            "x_status": "ok",
            "entry_snapshot": {"bundle_cluster_score": 0.66, "first30s_buy_ratio": 0.72, "x_validation_score": 71.4},
            "bundle_cluster_score": 0.66,
            "first30s_buy_ratio": 0.72,
            "x_validation_score": 71.4,
            "liquidity_usd": 22000,
        },
        {
            "position_id": "pos_1",
            "token_address": "So111",
            "side": "sell",
            "status": "filled",
            "timestamp": "2026-03-15T12:31:04Z",
            "exit_reason": "scalp_momentum_decay_after_recheck",
            "net_pnl_sol": 0.00063,
            "gross_pnl_sol": 0.00078,
            "fees_paid_sol": 0.00002,
            "slippage_bps": 160,
            "priority_fee_sol": 0.00002,
            "slippage_cost_sol_est": 0.00003,
        },
    ]
    signals = [{"signal_id": "sig1", "token_address": "So111", "status": "emitted"}]
    positions = [{"position_id": "pos_1", "token_address": "So111", "status": "closed"}]
    portfolio_state = {
        "starting_equity_sol": 0.10,
        "equity_sol": 0.10063,
        "unrealized_pnl_sol": 0.0,
        "total_signals": 1,
        "total_entries_attempted": 1,
        "total_fills_successful": 1,
        "total_positions_open": 0,
    }

    _write_jsonl(trades_dir / "trades.jsonl", trades)
    _write_jsonl(signals_dir / "signals.jsonl", signals)
    write_json(positions_dir / "positions.json", positions)
    write_json(processed_dir / "portfolio_state.json", portfolio_state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="data/smoke/post_run", help="Base fixture directory")
    args = parser.parse_args()

    root = Path(args.base_dir).expanduser().resolve()
    _prepare_fixture(root)

    import os

    os.environ["TRADES_DIR"] = str(root / "trades")
    os.environ["SIGNALS_DIR"] = str(root / "signals")
    os.environ["POSITIONS_DIR"] = str(root / "positions")
    os.environ["PROCESSED_DATA_DIR"] = str(root / "processed")

    settings = load_settings()
    result = run_post_run_analysis(settings)

    processed = root / "processed"
    (processed / "post_run_summary.smoke.json").write_text((processed / "post_run_summary.json").read_text(encoding="utf-8"), encoding="utf-8")
    (processed / "post_run_recommendations.smoke.json").write_text((processed / "post_run_recommendations.json").read_text(encoding="utf-8"), encoding="utf-8")
    (processed / "post_run_report.smoke.md").write_text((processed / "post_run_report.md").read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
