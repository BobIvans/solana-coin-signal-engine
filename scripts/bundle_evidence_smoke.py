"""Deterministic smoke runner for bundle evidence collection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from collectors.bundle_detector import detect_bundle_metrics_for_pair
from collectors.bundle_evidence_collector import collect_bundle_evidence_for_pair
from config.settings import load_settings
from utils.io import append_jsonl, ensure_dir, write_json


FIXTURE_PAIR = {
    "pair_address": "pair-smoke-1",
    "token_address": "token-smoke-1",
    "pair_created_at_ts": 1_000,
    "creator_wallet": "creator-smoke",
    "bundle_activity": [
        {"record_id": "r1", "group_id": "g1", "attempt_id": "a1", "wallet": "wallet-a", "status": "landed", "side": "buy", "timestamp": 1_003, "slot": 301, "bundle_value": 100.0, "tip_amount": 0.2},
        {"record_id": "r2", "group_id": "g1", "attempt_id": "a2", "wallet": "wallet-b", "status": "landed", "side": "buy", "timestamp": 1_004, "slot": 301, "bundle_value": 50.0, "tip_amount": 0.1},
        {"record_id": "r3", "group_id": "g2", "attempt_id": "a3", "wallet": "wallet-a", "status": "failed", "retry_of": None, "side": "buy", "timestamp": 1_020, "slot": 302, "bundle_value": 25.0, "tip_amount": 0.05},
        {"record_id": "r4", "group_id": "g2", "attempt_id": "a4", "wallet": "wallet-a", "status": "landed", "retry_of": "a3", "side": "buy", "timestamp": 1_021, "slot": 303, "bundle_value": 30.0, "tip_amount": 0.06},
    ],
}


def main() -> int:
    settings = load_settings()
    ensure_dir(settings.SMOKE_DIR)
    ensure_dir(settings.PROCESSED_DATA_DIR)

    evidence = collect_bundle_evidence_for_pair(FIXTURE_PAIR, now_ts=1_040, settings=settings)
    metrics = detect_bundle_metrics_for_pair(FIXTURE_PAIR, now_ts=1_040, settings=settings)
    summary = {
        "pair_address": FIXTURE_PAIR["pair_address"],
        "token_address": FIXTURE_PAIR["token_address"],
        "bundle_evidence_status": evidence.get("bundle_evidence_status"),
        "bundle_evidence_source": evidence.get("bundle_evidence_source"),
        "bundle_metric_origin": metrics.get("bundle_metric_origin"),
        "bundle_evidence_confidence": metrics.get("bundle_evidence_confidence"),
        "bundle_count_first_60s": metrics.get("bundle_count_first_60s"),
        "bundle_success_rate": metrics.get("bundle_success_rate"),
        "bundle_tip_efficiency": metrics.get("bundle_tip_efficiency"),
        "bundle_failure_retry_pattern": metrics.get("bundle_failure_retry_pattern"),
        "cross_block_bundle_correlation": metrics.get("cross_block_bundle_correlation"),
    }

    write_json(settings.SMOKE_DIR / "bundle_evidence.smoke.json", {"evidence": evidence, "metrics": metrics, "summary": summary})
    write_json(settings.SMOKE_DIR / "bundle_evidence_status.json", summary)
    events_path = settings.SMOKE_DIR / "bundle_evidence_events.jsonl"
    append_jsonl(events_path, {"event": "bundle_evidence_smoke", "summary": summary})
    for record in evidence.get("bundle_records", []):
        append_jsonl(events_path, {"event": "bundle_record", "pair_address": FIXTURE_PAIR["pair_address"], "record": record})

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
