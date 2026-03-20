#!/usr/bin/env python3
"""Historical replay driver for the canonical artifact-backed harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.replay.historical_replay_harness import run_historical_replay
from utils.io import ensure_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/replay.default.yaml")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--wallet-weighting", choices=["off", "shadow", "on"], default="off")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-ts", default=None)
    parser.add_argument("--end-ts", default=None)
    parser.add_argument("--artifact-dir", default="data/processed")
    parser.add_argument("--output-base-dir", default="runs")
    parser.add_argument("--allow-synthetic-smoke", action="store_true")
    args = parser.parse_args()

    ensure_dir(args.output_base_dir)
    result = run_historical_replay(
        artifact_dir=args.artifact_dir,
        run_id=args.run_id,
        config_path=args.config,
        wallet_weighting="on" if args.wallet_weighting == "shadow" else args.wallet_weighting,
        dry_run=args.dry_run,
        output_base_dir=args.output_base_dir,
        allow_synthetic_smoke=args.allow_synthetic_smoke,
    )
    summary = result["summary"]
    print(json.dumps({
        "run_id": args.run_id,
        "replay_mode": summary["replay_mode"],
        "historical_rows_used": summary["historical_rows_used"],
        "partial_rows": summary["partial_rows"],
        "unresolved_rows": summary["unresolved_rows"],
        "synthetic_fallback_used": summary["synthetic_fallback_used"],
        "wallet_weighting": args.wallet_weighting,
    }, sort_keys=True))
    print(f"[replay] done run_id={args.run_id} replay_mode={summary['replay_mode']} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
