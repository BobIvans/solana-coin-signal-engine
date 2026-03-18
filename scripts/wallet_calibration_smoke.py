"""Smoke runner for wallet weighting calibration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.wallet_weighting_calibration import run_wallet_weighting_calibration
from utils.io import ensure_dir, write_json


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    ensure_dir(path.parent)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _scored_payload(rows: list[dict], generated_at: str) -> dict:
    return {
        "contract_version": "unified_score_v1",
        "generated_at": generated_at,
        "tokens": rows,
    }


def _prepare_fixture(processed_dir: Path) -> None:
    ensure_dir(processed_dir)
    generated_at = "2026-03-18T10:00:00Z"
    off_rows = [
        {"token_address": "tok_a", "final_score": 71.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 68.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 59.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 0.0, "registry_status": "ok"}},
    ]
    shadow_rows = [
        {"token_address": "tok_a", "final_score": 72.5, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 1.5, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 69.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 1.0, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 58.5, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": -0.5, "registry_status": "ok"}},
    ]
    on_rows = [
        {"token_address": "tok_a", "final_score": 74.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 3.0, "registry_status": "ok"}},
        {"token_address": "tok_b", "final_score": 70.5, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": 2.5, "registry_status": "ok"}},
        {"token_address": "tok_c", "final_score": 57.0, "scored_at": generated_at, "wallet_adjustment": {"applied_delta": -2.0, "registry_status": "ok"}},
    ]
    write_json(processed_dir / "scored_tokens.off.json", _scored_payload(off_rows, generated_at))
    write_json(processed_dir / "scored_tokens.shadow.json", _scored_payload(shadow_rows, generated_at))
    write_json(processed_dir / "scored_tokens.on.json", _scored_payload(on_rows, generated_at))

    for mode, pnls in {
        "off": [0.2, -0.1, 0.1, -0.2, 0.15],
        "shadow": [0.25, -0.05, 0.12, -0.1, 0.14],
        "on": [0.4, -0.02, 0.2, -0.05, 0.18],
    }.items():
        positions = []
        mode_dir = ensure_dir(processed_dir / mode)
        for index, pnl in enumerate(pnls, start=1):
            positions.append(
                {
                    "position_id": f"{mode}_{index}",
                    "token_address": f"{mode}_token_{index}",
                    "status": "closed",
                    "net_pnl_pct": pnl,
                    "gross_pnl_pct": pnl + 0.01,
                    "closed_at": f"2026-03-18T10:0{index}:00Z",
                }
            )
        write_json(mode_dir / "positions.json", positions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--out-report", default="data/processed/wallet_calibration_report.json")
    parser.add_argument("--out-md", default="data/processed/wallet_calibration_summary.md")
    parser.add_argument("--out-recommendation", default="data/processed/wallet_rollout_recommendation.json")
    parser.add_argument("--off-scored", default=None)
    parser.add_argument("--shadow-scored", default=None)
    parser.add_argument("--on-scored", default=None)
    parser.add_argument("--off-base-dir", default=None)
    parser.add_argument("--shadow-base-dir", default=None)
    parser.add_argument("--on-base-dir", default=None)
    parser.add_argument("--max-top-n", type=int, default=25)
    parser.add_argument("--min-trades-medium-confidence", type=int, default=20)
    parser.add_argument("--min-trades-high-confidence", type=int, default=50)
    args = parser.parse_args()

    processed_dir = Path(args.processed_dir).expanduser().resolve()
    _prepare_fixture(processed_dir)
    report = run_wallet_weighting_calibration(
        processed_dir=processed_dir,
        out_report=Path(args.out_report),
        out_md=Path(args.out_md),
        out_recommendation=Path(args.out_recommendation),
        off_scored=Path(args.off_scored).expanduser().resolve() if args.off_scored else None,
        shadow_scored=Path(args.shadow_scored).expanduser().resolve() if args.shadow_scored else None,
        on_scored=Path(args.on_scored).expanduser().resolve() if args.on_scored else None,
        off_base_dir=Path(args.off_base_dir).expanduser().resolve() if args.off_base_dir else processed_dir / "off",
        shadow_base_dir=Path(args.shadow_base_dir).expanduser().resolve() if args.shadow_base_dir else processed_dir / "shadow",
        on_base_dir=Path(args.on_base_dir).expanduser().resolve() if args.on_base_dir else processed_dir / "on",
        max_top_n=args.max_top_n,
        min_trades_medium_confidence=args.min_trades_medium_confidence,
        min_trades_high_confidence=args.min_trades_high_confidence,
    )
    print(json.dumps(report["recommendation"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
