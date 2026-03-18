#!/usr/bin/env python3
"""Evaluate smart wallet registry tiers against local replay artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from analytics.wallet_replay_validation import (
    MAX_HOT_VALIDATED_DEFAULT,
    MIN_SAMPLE_TIER_1_DEFAULT,
    MIN_SAMPLE_TIER_2_DEFAULT,
    ReplayInputError,
    ValidationThresholds,
    evaluate_wallet_registry_replay,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, help="Path to smart_wallets.json")
    parser.add_argument("--processed-dir", required=True, help="Directory with local replay artifacts")
    parser.add_argument("--out-report", required=True, help="Path for replay validation report")
    parser.add_argument("--out-registry", required=True, help="Path for validated smart wallet registry")
    parser.add_argument("--out-hot", required=True, help="Path for validated hot wallet subset")
    parser.add_argument(
        "--event-log",
        default="data/registry/promotion_events.jsonl",
        help="Append-only promotion event log path",
    )
    parser.add_argument("--generated-at", default=None, help="Deterministic timestamp override")
    parser.add_argument("--max-hot", type=int, default=MAX_HOT_VALIDATED_DEFAULT, help="Maximum validated hot wallets")
    parser.add_argument("--min-sample-tier2", type=int, default=MIN_SAMPLE_TIER_2_DEFAULT, help="Minimum wallet-specific replay sample for tier_2 promotion")
    parser.add_argument("--min-sample-tier1", type=int, default=MIN_SAMPLE_TIER_1_DEFAULT, help="Minimum wallet-specific replay sample for tier_1 promotion")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = ValidationThresholds(
        max_hot_validated=args.max_hot,
        min_sample_tier2=args.min_sample_tier2,
        min_sample_tier1=args.min_sample_tier1,
    )
    try:
        result = evaluate_wallet_registry_replay(
            registry_path=args.registry,
            processed_dir=args.processed_dir,
            out_report=args.out_report,
            out_registry=args.out_registry,
            out_hot=args.out_hot,
            event_log=args.event_log,
            generated_at=args.generated_at,
            thresholds=thresholds,
        )
    except ReplayInputError as exc:
        print(f"Replay validation failed: {exc}", file=sys.stderr)
        return 2

    report = result["report"]
    print("Wallet replay validation complete")
    print(f"- report: {args.out_report}")
    print(f"- registry: {args.out_registry}")
    print(f"- hot: {args.out_hot}")
    print(f"- event_log: {result['event_log']}")
    print(
        "- summary: "
        f"promoted={report['promotion_summary']['promote']} "
        f"demoted={report['promotion_summary']['demote']} "
        f"held={report['promotion_summary']['hold']} "
        f"watch_pending_validation={report['promotion_summary']['watch_pending_validation']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
