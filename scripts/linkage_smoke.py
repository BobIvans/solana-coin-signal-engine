#!/usr/bin/env python3
"""Deterministic smoke runner for creator/dev/funder linkage scoring."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from analytics.linkage_scorer import score_creator_dev_funder_linkage
from utils.clock import utc_now_iso
from utils.io import append_jsonl, ensure_dir, write_json


def _fixture() -> dict[str, object]:
    participants = [
        {"wallet": "creator_wallet", "funder": "funder_alpha", "cluster_id": "cluster_1", "launch_group": "launch_a", "creator_linked": True},
        {"wallet": "dev_wallet", "funder": "funder_alpha", "cluster_id": "cluster_2", "launch_group": "launch_a", "dev_linked": True},
        {"wallet": "buyer_1", "funder": "funder_alpha", "cluster_id": "cluster_1", "launch_group": "launch_a", "creator_linked": True},
        {"wallet": "buyer_2", "funder": "funder_beta", "cluster_id": "cluster_2", "launch_group": "launch_a", "dev_linked": True},
    ]
    return {
        "token_address": "token_smoke_linkage",
        "pair_address": "pair_smoke_linkage",
        "creator_wallet": "creator_wallet",
        "dev_wallet": "dev_wallet",
        "early_buyer_wallets": ["buyer_1", "buyer_2"],
        "participants": participants,
        "cluster_ids_by_wallet": {
            "creator_wallet": "cluster_1",
            "dev_wallet": "cluster_2",
            "buyer_1": "cluster_1",
            "buyer_2": "cluster_2",
        },
    }


def main() -> int:
    fixture = _fixture()
    scored = score_creator_dev_funder_linkage(
        fixture["participants"],
        creator_wallet=fixture["creator_wallet"],
        dev_wallet=fixture["dev_wallet"],
        early_buyer_wallets=fixture["early_buyer_wallets"],
        cluster_ids_by_wallet=fixture["cluster_ids_by_wallet"],
        token_address=fixture["token_address"],
        pair_address=fixture["pair_address"],
    )
    timestamp = utc_now_iso()
    smoke_dir = ensure_dir(REPO_ROOT / "data" / "smoke")
    score_path = smoke_dir / "linkage_score.smoke.json"
    status_path = smoke_dir / "linkage_status.json"
    events_path = smoke_dir / "linkage_events.jsonl"

    write_json(
        score_path,
        {
            "metadata": {
                "schema_name": "linkage_score",
                "schema_version": "linkage_score.v1",
                "producer": "scripts/linkage_smoke.py",
            },
            "contract_version": "linkage_score_v1",
            "generated_at": timestamp,
            "token_pair_linkage": {
                "token_address": fixture["token_address"],
                "pair_address": fixture["pair_address"],
                "symbol": None,
            },
            **scored,
        },
    )
    write_json(
        status_path,
        {
            "generated_at": timestamp,
            "token_address": fixture["token_address"],
            "pair_address": fixture["pair_address"],
            "linkage_status": scored.get("linkage_status"),
            "linkage_warning": scored.get("linkage_warning"),
            "linkage_confidence": scored.get("linkage_confidence"),
            "reason_codes": scored.get("linkage_reason_codes"),
        },
    )
    for event_name in (
        "linkage_scoring_started",
        "linkage_score_computed",
        "linkage_completed",
    ):
        append_jsonl(
            events_path,
            {
                "ts": timestamp,
                "event": event_name,
                "token_address": fixture["token_address"],
                "pair_address": fixture["pair_address"],
                "linkage_status": scored.get("linkage_status"),
                "linkage_confidence": scored.get("linkage_confidence"),
                "overlap_count": scored.get("funder_overlap_count"),
                "warning": scored.get("linkage_warning"),
            },
        )
    print(json.dumps({
        "token_address": fixture["token_address"],
        "pair_address": fixture["pair_address"],
        "linkage_risk_score": scored.get("linkage_risk_score"),
        "linkage_confidence": scored.get("linkage_confidence"),
        "linkage_status": scored.get("linkage_status"),
        "reason_codes": scored.get("linkage_reason_codes"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
