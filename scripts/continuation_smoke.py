#!/usr/bin/env python3
"""Deterministic local smoke runner for continuation enrichment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analytics.continuation_enricher import build_continuation_payload
from config.settings import load_settings
from utils.io import append_jsonl, ensure_dir, write_json


def _fixture() -> dict:
    return {
        "token": {
            "token_address": "mint-smoke-1",
            "pair_address": "pair-smoke-1",
            "pair_created_at": "1970-01-01T00:16:40Z",
            "creator_wallet": "creator-smoke",
            "symbol": "SMK",
            "name": "SmokeToken",
        },
        "txs": [
            # Continuation smoke intentionally uses explicit success=True because
            # tx-derived continuation metrics are gated on clearly successful txs.
            {
                "timestamp": 1000,
                "success": True,
                "liquidity_usd": 100.0,
                "participants": [
                    {"wallet": "buyer_a", "funder": "shared_a"},
                    {"wallet": "buyer_b", "funder": "shared_a"},
                    {"wallet": "buyer_c", "funder": "shared_c"}
                ],
                "tokenTransfers": [
                    {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 6},
                    {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 6},
                    {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_c", "tokenAmount": 5}
                ]
            },
            {
                "timestamp": 1025,
                "success": True,
                "success": True,
                "liquidity_usd": 60.0,
                "tokenTransfers": [
                    {"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 18},
                    {"fromUserAccount": "buyer_b", "toUserAccount": "lp_pool", "tokenAmount": 12}
                ]
            },
            {
                "timestamp": 1050,
                "success": True,
                "success": True,
                "liquidity_usd": 100.0,
                "tokenTransfers": [
                    {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 4}
                ]
            }
        ],
        "x_snapshots": [
            {
                "x_status": "ok",
                "cards": [
                    {"author_handle": "@alpha", "created_at": "1970-01-01T00:16:40Z"},
                    {"author_handle": "@beta", "created_at": "1970-01-01T00:18:00Z"},
                    {"author_handle": "@gamma", "created_at": "1970-01-01T00:20:00Z"}
                ]
            }
        ],
        "wallet_lookup": {
            "validated_wallets": {
                "buyer_a": {"wallet": "buyer_a", "tier": "tier_1", "family_id": "fam_a", "cluster_id": "cluster_a"},
                "buyer_b": {"wallet": "buyer_b", "tier": "tier_2", "family_id": "fam_b", "cluster_id": "cluster_b"},
                "buyer_c": {"wallet": "buyer_c", "tier": "tier_3", "family_id": "fam_c", "cluster_id": "cluster_c"}
            }
        },
        "hit_wallets": ["buyer_a", "buyer_b", "buyer_c"]
    }


def main() -> int:
    settings = load_settings()
    smoke_dir = settings.SMOKE_DIR
    ensure_dir(smoke_dir)

    fixture = _fixture()
    payload = build_continuation_payload(
        token_ctx=fixture["token"],
        txs=fixture["txs"],
        x_snapshots=fixture["x_snapshots"],
        wallet_lookup=fixture["wallet_lookup"],
        hit_wallets=fixture["hit_wallets"],
    )

    write_json(smoke_dir / "continuation_enrichment.smoke.json", payload)
    write_json(smoke_dir / "continuation_status.json", payload["provenance"])
    events_path = smoke_dir / "continuation_events.jsonl"
    if events_path.exists():
        events_path.unlink()
    for event in payload["events"]:
        append_jsonl(events_path, event)

    summary = {
        "token_address": payload["token"]["token_address"],
        "continuation_status": payload["provenance"]["continuation_status"],
        "continuation_confidence": payload["provenance"]["continuation_confidence"],
        "continuation_metric_origin": payload["provenance"]["continuation_metric_origin"],
        "continuation_coverage_ratio": payload["provenance"]["continuation_coverage_ratio"],
        **payload["continuation_metrics"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
