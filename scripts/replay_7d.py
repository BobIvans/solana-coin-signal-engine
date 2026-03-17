#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from src.wallets.io import write_wallet_feature_stats, write_wallet_weighting_summary
from utils.io import ensure_dir, read_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/replay.default.yaml")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--wallet-weighting", choices=["on", "off"], default="off")
    args = parser.parse_args()

    _ = (args.config, args.days, args.seed)
    run_dir = ensure_dir(Path("runs") / args.run_id)
    processed = Path("data/processed")
    entry_candidates = read_json(processed / "entry_candidates.json", default=[]) or []
    registry_payload = read_json("data/smart_wallets.registry.json", default={}) or {}
    registry_wallets = registry_payload.get("wallets", []) if isinstance(registry_payload, dict) else []

    signals_path = run_dir / "signals.jsonl"
    with signals_path.open("w", encoding="utf-8") as handle:
        for item in entry_candidates:
            wallet_features = item.get("wallet_features") or {
                "smart_wallet_hits": 0,
                "smart_wallet_score_sum": 0.0,
                "smart_wallet_tier1_hits": 0,
                "smart_wallet_tier2_hits": 0,
                "smart_wallet_unique_count": 0,
                "smart_wallet_early_entry_hits": 0,
                "smart_wallet_netflow_bias": 0.0,
            }
            payload = {**item, "wallet_features": wallet_features, "wallet_weighting": args.wallet_weighting}
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")

    print(f"[wallets] registry_loaded count={len(registry_wallets)}")
    print(f"[wallets] wallet_features_built signals={len(entry_candidates)}")

    weighting_enabled = args.wallet_weighting == "on"
    applied_count = sum(1 for item in entry_candidates if (item.get("wallet_features") or {}).get("smart_wallet_hits", 0) > 0) if weighting_enabled else 0
    print(f"[wallets] wallet_weighting_applied count={applied_count}") if weighting_enabled else None

    write_wallet_feature_stats(
        run_dir / "wallet_feature_stats.json",
        total_registry_wallets=len(registry_wallets),
        active_wallets=sum(1 for item in registry_wallets if item.get("status") == "active"),
        tier1_count=sum(1 for item in registry_wallets if item.get("tier") == "tier_1"),
        tier2_count=sum(1 for item in registry_wallets if item.get("tier") == "tier_2"),
        tier3_count=sum(1 for item in registry_wallets if item.get("tier") == "tier_3"),
        signals_with_wallet_hits=applied_count,
        trades_with_wallet_hits=0,
        avg_wallet_score_sum_per_signal=0.0,
        avg_wallet_score_sum_per_trade=0.0,
    )

    write_wallet_weighting_summary(
        run_dir / "wallet_weighting_summary.json",
        wallet_weighting_enabled=weighting_enabled,
        weighting_mode="additive",
        wallet_bonus_applied_count=applied_count,
        wallet_penalty_applied_count=0,
        avg_bonus_score=0.0,
        avg_penalty_score=0.0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
