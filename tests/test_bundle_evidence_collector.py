import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.bundle_evidence_collector import (
    compute_bundle_metrics_from_evidence,
    collect_bundle_evidence_for_pair,
    normalize_bundle_evidence,
)


class DummySettings:
    BUNDLE_ENRICHMENT_ENABLED = True
    BUNDLE_ENRICHMENT_WINDOW_SEC = 60
    BUNDLE_EVIDENCE_ENABLED = True
    BUNDLE_EVIDENCE_MAX_RECORDS = 200
    BUNDLE_EVIDENCE_WINDOW_SEC = 60
    BUNDLE_EVIDENCE_SOURCE_ORDER = "inline,activity,events,flows,attempts"


PAIR = {
    "pair_address": "pair-1",
    "token_address": "token-1",
    "pair_created_at_ts": 1_000,
    "creator_wallet": "creator-1",
}


def test_strong_early_landed_buy_only_evidence_fixture():
    pair = {
        **PAIR,
        "bundle_activity": [
            {"record_id": "r1", "group_id": "g1", "attempt_id": "a1", "wallet": "w1", "status": "landed", "side": "buy", "timestamp": 1_003, "slot": 101, "bundle_value": 100.0, "tip_amount": 0.2},
            {"record_id": "r2", "group_id": "g1", "attempt_id": "a2", "wallet": "w2", "status": "landed", "side": "buy", "timestamp": 1_004, "slot": 101, "bundle_value": 50.0, "tip_amount": 0.1},
            {"record_id": "r3", "group_id": "g2", "attempt_id": "a3", "wallet": "w3", "status": "landed", "side": "buy", "timestamp": 1_020, "slot": 102, "bundle_value": 75.0, "tip_amount": 0.15},
            {"record_id": "r4", "group_id": "g2", "attempt_id": "a4", "wallet": "w4", "status": "landed", "side": "buy", "timestamp": 1_021, "slot": 102, "bundle_value": 25.0, "tip_amount": 0.05},
        ],
    }

    evidence = collect_bundle_evidence_for_pair(pair, now_ts=1_040, settings=DummySettings())
    metrics = compute_bundle_metrics_from_evidence(evidence, pair=pair)

    assert evidence["bundle_evidence_status"] == "ok"
    assert metrics["bundle_metric_origin"] == "direct_evidence"
    assert metrics["bundle_count_first_60s"] == 2
    assert metrics["bundle_composition_dominant"] == "buy-only"
    assert metrics["bundle_tip_efficiency"] == 0.002
    assert metrics["bundle_success_rate"] == 1.0
    assert metrics["bundle_evidence_confidence"] is not None


def test_failed_retry_heavy_pattern_uses_real_evidence():
    pair = {
        **PAIR,
        "bundle_activity": [
            {"record_id": "r1", "group_id": "g1", "attempt_id": "a1", "wallet": "w1", "status": "failed", "retry_of": None, "side": "buy", "timestamp": 1_005, "slot": 110, "bundle_value": 100.0, "tip_amount": 0.2},
            {"record_id": "r2", "group_id": "g1", "attempt_id": "a2", "wallet": "w1", "status": "retry", "retry_of": "a1", "side": "buy", "timestamp": 1_010, "slot": 111, "bundle_value": 100.0, "tip_amount": 0.2},
            {"record_id": "r3", "group_id": "g1", "attempt_id": "a3", "wallet": "w2", "status": "landed", "side": "buy", "timestamp": 1_012, "slot": 111, "bundle_value": 120.0, "tip_amount": 0.25},
            {"record_id": "r4", "group_id": "g2", "attempt_id": "a4", "wallet": "w1", "status": "failed", "retry_of": None, "side": "buy", "timestamp": 1_030, "slot": 112, "bundle_value": 50.0, "tip_amount": 0.1},
            {"record_id": "r5", "group_id": "g2", "attempt_id": "a5", "wallet": "w1", "status": "landed", "retry_of": "a4", "side": "buy", "timestamp": 1_035, "slot": 112, "bundle_value": 55.0, "tip_amount": 0.1},
        ],
    }

    evidence = collect_bundle_evidence_for_pair(pair, now_ts=1_050, settings=DummySettings())
    metrics = compute_bundle_metrics_from_evidence(evidence, pair=pair)

    assert metrics["bundle_metric_origin"] == "direct_evidence"
    assert metrics["bundle_failure_retry_pattern"] > 0
    assert metrics["bundle_evidence_warning"] is not None or evidence["bundle_evidence_warning"] is not None or evidence["bundle_evidence_status"] in {"ok", "partial"}


def test_cross_block_coordination_fixture():
    pair = {
        **PAIR,
        "bundle_activity": [
            {"record_id": "r1", "group_id": "g1", "wallet": "w1", "status": "landed", "side": "buy", "timestamp": 1_002, "slot": 201, "bundle_value": 100.0},
            {"record_id": "r2", "group_id": "g1", "wallet": "w2", "status": "landed", "side": "buy", "timestamp": 1_003, "slot": 201, "bundle_value": 90.0},
            {"record_id": "r3", "group_id": "g2", "wallet": "w1", "status": "landed", "side": "buy", "timestamp": 1_015, "slot": 202, "bundle_value": 85.0},
            {"record_id": "r4", "group_id": "g2", "wallet": "w2", "status": "landed", "side": "buy", "timestamp": 1_016, "slot": 203, "bundle_value": 80.0},
        ],
    }

    evidence = collect_bundle_evidence_for_pair(pair, now_ts=1_050, settings=DummySettings())
    metrics = compute_bundle_metrics_from_evidence(evidence, pair=pair)

    assert metrics["bundle_metric_origin"] == "direct_evidence"
    assert metrics["cross_block_bundle_correlation"] is not None


def test_malformed_evidence_degrades_safely():
    raw_records = [
        {"wallet": "w1", "status": "mystery-status", "timestamp": None, "slot": None, "bundle_value": "nan"},
        {"wallet": "", "status": "landed", "timestamp": None, "slot": None},
    ]
    evidence = normalize_bundle_evidence(raw_records, pair=PAIR, anchor_ts=1_000, window_sec=60, source="activity", collected_at="2026-03-19T00:00:00Z")
    metrics = compute_bundle_metrics_from_evidence(evidence, pair=PAIR)

    assert evidence["bundle_evidence_status"] == "partial"
    assert "missing timestamp" in str(evidence["bundle_evidence_warning"])
    assert metrics["bundle_metric_origin"] == "missing"
    assert metrics["bundle_count_first_60s"] is None
    json.dumps(evidence)
