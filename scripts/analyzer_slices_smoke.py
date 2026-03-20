"""Deterministic smoke runner for richer analyzer slices."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer import run_post_run_analysis
from config.settings import load_settings
from utils.io import ensure_dir, read_json, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _matrix_rows() -> list[dict]:
    rows: list[dict] = []
    fixtures = [
        ("p1", "TREND", -8.5, 120, 0.84, True, 0.82, 1, 0.22, 0.78, 240, "degraded", 0.30, True, "cluster_dump"),
        ("p2", "TREND", -4.0, 180, 0.79, True, 0.70, 1, 0.26, 0.71, 220, "degraded", 0.35, True, "creator_cluster_exit"),
        ("p3", "TREND", 10.0, 900, 0.88, False, 0.28, 3, 0.18, 0.22, 70, "healthy", 1.20, False, "trend_take_profit"),
        ("p4", "SCALP", 2.0, 150, 0.61, False, 0.20, 2, 0.21, 0.25, 65, "healthy", 1.10, False, "scalp_take_profit"),
        ("p5", "SCALP", 1.5, 170, 0.59, False, 0.24, 3, 0.24, 0.28, 80, "healthy", 1.30, False, "scalp_take_profit"),
        ("p6", "SCALP", -1.0, 100, 0.55, False, 0.22, 2, 0.20, 0.30, 90, "degraded", 0.40, False, "scalp_stop_loss"),
    ]
    for position_id, regime, pnl, hold_sec, confidence, creator, concentration, clusters, reentry, cluster_sell, recovery, x_status, size_sol, retry, exit_reason in fixtures:
        rows.append(
            {
                "position_id": position_id,
                "regime_decision": regime,
                "net_pnl_pct": pnl,
                "hold_sec": hold_sec,
                "regime_confidence": confidence,
                "mfe_pct": pnl + (12.0 if regime == "SCALP" else 2.0),
                "trend_survival_15m": 0.78 if regime == "SCALP" and pnl > 0 else 0.18,
                "trend_survival_60m": 0.62 if regime == "SCALP" and pnl > 0 else 0.10,
                "liquidity_refill_ratio_120s": 1.10 if pnl > 0 else 0.55,
                "seller_reentry_ratio": reentry,
                "liquidity_shock_recovery_sec": recovery,
                "cluster_sell_concentration_120s": cluster_sell,
                "net_unique_buyers_60s": 18 if pnl > 0 else 8,
                "smart_wallet_dispersion_score": 0.70 if pnl > 0 else 0.24,
                "x_author_velocity_5m": 0.68 if pnl > 0 else 0.16,
                "creator_in_cluster_flag": creator,
                "creator_cluster_penalty": 0.86 if creator else 0.12,
                "single_cluster_penalty": 0.74 if clusters == 1 else 0.12,
                "cluster_concentration_ratio": concentration,
                "num_unique_clusters_first_60s": clusters,
                "organic_multi_cluster_bonus": 0.52 if clusters >= 2 else 0.0,
                "bundle_sell_heavy_penalty": 0.82 if pnl < 0 else 0.10,
                "retry_manipulation_penalty": 0.79 if retry else 0.06,
                "bundle_failure_retry_pattern": "retry_heavy" if retry else "clean",
                "bundle_composition_dominant": "sell_only" if pnl < 0 else "mixed",
                "cross_block_bundle_correlation": 0.80 if pnl < 0 else 0.18,
                "bundle_tip_efficiency": 0.25 if pnl < 0 else 0.66,
                "x_status": x_status,
                "size_sol": size_sol,
                "exit_reason_final": exit_reason,
                "partial_exit_count": 1 if pnl > 0 and regime == "SCALP" else 0,
            }
        )
    return rows


def _prepare_fixture(base_dir: Path) -> None:
    ensure_dir(base_dir)
    trades = [
        {
            "position_id": "p0",
            "token_address": "So111",
            "side": "buy",
            "status": "filled",
            "timestamp": "2026-03-15T12:30:00Z",
            "regime": "SCALP",
            "size_sol": 0.20,
            "entry_snapshot": {"bundle_cluster_score": 0.55, "first30s_buy_ratio": 0.60, "x_validation_score": 70},
        },
        {
            "position_id": "p0",
            "token_address": "So111",
            "side": "sell",
            "status": "filled",
            "timestamp": "2026-03-15T12:31:00Z",
            "exit_reason": "scalp_take_profit",
            "net_pnl_sol": 0.0008,
            "gross_pnl_sol": 0.0010,
        },
    ]
    _write_jsonl(base_dir / "trades.jsonl", trades)
    _write_jsonl(base_dir / "signals.jsonl", [{"signal_id": "sig-1", "token_address": "So111"}])
    write_json(base_dir / "positions.json", [{"position_id": "p0", "status": "closed"}])
    write_json(base_dir / "portfolio_state.json", {"starting_equity_sol": 0.10, "equity_sol": 0.1008, "unrealized_pnl_sol": 0.0})
    _write_jsonl(base_dir / "trade_feature_matrix.jsonl", _matrix_rows())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="data/smoke", help="Directory used for deterministic analyzer-slice smoke artifacts")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).expanduser().resolve()
    smoke_dir = ensure_dir(base_dir)
    _prepare_fixture(smoke_dir)

    os.environ["TRADES_DIR"] = str(smoke_dir)
    os.environ["SIGNALS_DIR"] = str(smoke_dir)
    os.environ["POSITIONS_DIR"] = str(smoke_dir)
    os.environ["PROCESSED_DATA_DIR"] = str(smoke_dir)
    os.environ["POST_RUN_MIN_TRADES_FOR_CORRELATION"] = "1"
    os.environ["POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON"] = "2"
    os.environ["POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION"] = "2"
    os.environ["POST_RUN_OUTLIER_CLIP_PCT"] = "0"

    result = run_post_run_analysis(load_settings())

    analyzer_slices_path = smoke_dir / "analyzer_slices.smoke.json"
    summary_markdown_path = smoke_dir / "analyzer_slices_summary.md"
    analyzer_payload = read_json(Path(result["analyzer_slices_path"]))
    analyzer_slices_path.write_text(json.dumps(analyzer_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_markdown_path.write_text(Path(result["report_path"]).read_text(encoding="utf-8"), encoding="utf-8")

    print(
        json.dumps(
            {
                "analyzer_slices_path": str(analyzer_slices_path),
                "summary_markdown_path": str(summary_markdown_path),
                "slice_groups": list(analyzer_payload.get("slice_groups", {}).keys()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
