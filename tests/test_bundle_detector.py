import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import collectors.bundle_detector as bundle_detector
from collectors.bundle_detector import (
    classify_bundle_composition,
    compute_advanced_bundle_fields,
    compute_bundle_tip_efficiency,
    compute_cross_block_bundle_correlation,
    detect_bundle_failure_retry_pattern,
)
from collectors.discovery_engine import build_shortlist, run_discovery_once

from collectors.bundle_detector import detect_bundle_metrics_for_pair, safe_null_bundle_metrics


class DummySettings:
    BUNDLE_ENRICHMENT_ENABLED = True
    BUNDLE_ENRICHMENT_WINDOW_SEC = 60
    HELIUS_API_KEY = ""
    HELIUS_TX_ADDR_LIMIT = 40


def test_detect_bundle_metrics_uses_first_window_fixture_transactions():
    pair = {
        "pair_created_at_ts": 1_000,
        "bundle_transactions": [
            {
                "timestamp": 1_002,
                "slot": 10,
                "feePayer": "wallet_a",
                "bundle_value": 100.0,
                "success": True,
                "funder": "funder_alpha",
            },
            {
                "timestamp": 1_002,
                "slot": 10,
                "feePayer": "wallet_b",
                "bundle_value": 50.0,
                "success": False,
                "funder": "funder_alpha",
            },
            {
                "timestamp": 1_030,
                "slot": 20,
                "feePayer": "wallet_c",
                "bundle_value": 25.0,
                "success": True,
                "funder": "funder_beta",
            },
            {
                "timestamp": 1_030,
                "slot": 20,
                "feePayer": "wallet_d",
                "bundle_value": 75.0,
                "success": True,
                "funder": "funder_beta",
            },
            {
                "timestamp": 1_075,
                "slot": 99,
                "feePayer": "wallet_z",
                "bundle_value": 999.0,
                "success": True,
            },
        ],
    }

    result = detect_bundle_metrics_for_pair(pair, now_ts=1_120, settings=DummySettings())

    assert result["bundle_enrichment_status"] == "ok"
    assert result["bundle_count_first_60s"] == 2
    assert result["bundle_size_value"] == 250.0
    assert result["unique_wallets_per_bundle_avg"] == 2.0
    assert result["bundle_timing_from_liquidity_add_min"] == round(2 / 60, 6)
    assert result["bundle_success_rate"] == 0.75
    assert result["cluster_concentration_ratio"] == 0.5
    assert result["num_unique_clusters_first_60s"] == 2
    assert result["bundle_wallet_clustering_score"] == 0.45
    assert result["creator_in_cluster_flag"] is None
    assert result["shared_funder_link_score"] > 0
    assert result["linkage_status"] in {"ok", "partial"}


def test_detect_bundle_metrics_is_honest_when_anchor_missing():
    result = detect_bundle_metrics_for_pair({}, now_ts=1_000, settings=DummySettings())

    assert result == safe_null_bundle_metrics(status="unavailable", warning="missing liquidity/pair creation anchor")


def test_classify_bundle_composition_variants():
    assert classify_bundle_composition([
        {"side": "buy"},
        {"action": "buy"},
    ]) == "buy-only"
    assert classify_bundle_composition([
        {"side": "buy"},
        {"side": "sell"},
    ]) == "mixed"
    assert classify_bundle_composition([
        {"side": "sell"},
        {"token_delta": -5},
    ]) == "sell-only"
    assert classify_bundle_composition([{}, {"status": "confirmed"}]) == "unknown"


def test_compute_bundle_tip_efficiency_requires_honest_evidence():
    records = [
        {"tip_amount": 0.2, "bundle_value": 100},
        {"tip_amount": 0.1, "bundle_value": 50},
    ]
    assert compute_bundle_tip_efficiency(records) == 0.002
    assert compute_bundle_tip_efficiency([{"bundle_value": 100}]) is None
    assert compute_bundle_tip_efficiency([{"tip_amount": 0.1}]) is None


def test_detect_bundle_failure_retry_pattern_counts_retries():
    assert detect_bundle_failure_retry_pattern([
        {"wallet": "w1", "status": "confirmed", "timestamp": 10},
    ]) == 0
    assert detect_bundle_failure_retry_pattern([
        {"wallet": "w1", "status": "failed", "timestamp": 10},
        {"wallet": "w1", "status": "retry", "timestamp": 20},
        {"wallet": "w1", "status": "confirmed", "timestamp": 25},
        {"wallet": "w2", "status": "failed", "timestamp": 30},
        {"wallet": "w2", "status": "retry", "timestamp": 40},
    ]) == 3
    assert detect_bundle_failure_retry_pattern([{"wallet": "w1"}]) is None


def test_compute_cross_block_bundle_correlation_variants():
    assert compute_cross_block_bundle_correlation([
        {"wallet": "solo", "slot": 101},
    ]) == 0.0
    assert compute_cross_block_bundle_correlation([
        {"wallet": "actor", "slot": 101},
        {"wallet": "actor", "slot": 102},
        {"wallet": "actor", "slot": 104},
    ]) == 1.0
    assert compute_cross_block_bundle_correlation([
        {"wallet": "actor", "slot": 101},
        {"wallet": "actor", "slot": 110},
    ]) == 0.0
    assert compute_cross_block_bundle_correlation([{"wallet": "actor"}]) is None


def test_compute_advanced_bundle_fields_uses_unknown_and_none_when_missing():
    out = compute_advanced_bundle_fields(candidate={"bundle_size_value": None}, raw_pair={})
    assert out == {
        "bundle_composition_dominant": "unknown",
        "bundle_tip_efficiency": None,
        "bundle_failure_retry_pattern": None,
        "cross_block_bundle_correlation": None,
    }


def test_discovery_smoke_enriches_candidates_and_shortlist(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("SMOKE_DIR", str(tmp_path / "smoke"))
    monkeypatch.setenv("X_MAX_TOKENS_PER_CYCLE", "2")

    raw_pair = {
        "pairAddress": "pair-1",
        "chainId": "solana",
        "dexId": "raydium",
        "pairCreatedAt": 900,
        "baseToken": {"address": "mint-1", "symbol": "BNDL", "name": "Bundle Coin"},
        "priceUsd": "0.1",
        "fdv": 300000,
        "marketCap": 0,
        "liquidity": {"usd": 25000},
        "volume": {"m5": 10000, "h1": 12000},
        "txns": {"m5": {"buys": 15, "sells": 10}},
        "bundle_activity": [
            {"wallet": "actor-1", "side": "buy", "tip_amount": 0.2, "bundle_value": 100, "status": "failed", "timestamp": 905, "slot": 1001},
            {"wallet": "actor-1", "side": "buy", "tip_amount": 0.1, "bundle_value": 50, "status": "retry", "timestamp": 915, "slot": 1002},
            {"wallet": "actor-1", "side": "buy", "tip_amount": 0.05, "bundle_value": 25, "status": "confirmed", "timestamp": 925, "slot": 1004},
        ],
    }

    monkeypatch.setattr("collectors.discovery_engine.fetch_latest_solana_pairs", lambda: [raw_pair])
    monkeypatch.setattr("collectors.discovery_engine.utc_now_ts", lambda: 1000)
    monkeypatch.setattr("collectors.discovery_engine.utc_now_iso", lambda: "2026-03-18T12:00:00Z")

    result = run_discovery_once()

    candidate = result["candidates"]["candidates"][0]
    shortlist_item = result["shortlist"]["shortlist"][0]

    for row in (candidate, shortlist_item):
        assert row["bundle_composition_dominant"] == "buy-only"
        assert row["bundle_tip_efficiency"] == 0.002
        assert row["bundle_failure_retry_pattern"] == 2
        assert row["cross_block_bundle_correlation"] == 1.0


def test_build_shortlist_preserves_missing_advanced_fields_without_crash():
    shortlist = build_shortlist([
        {"token_address": "tok-1", "pair_address": "pair-1", "fast_prescore": 50, "volume_m5": 10},
    ], top_k=1)
    item = shortlist[0]
    assert item["bundle_composition_dominant"] is None
    assert item["bundle_tip_efficiency"] is None
    assert item["bundle_failure_retry_pattern"] is None
    assert item["cross_block_bundle_correlation"] is None


def test_detect_bundle_metrics_keeps_heuristics_but_degrades_stale_tx_source(monkeypatch):
    class ProvenanceSettings:
        BUNDLE_ENRICHMENT_ENABLED = True
        BUNDLE_ENRICHMENT_WINDOW_SEC = 60
        HELIUS_API_KEY = "dummy"
        HELIUS_TX_ADDR_LIMIT = 40

    class DummyHelius:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_transactions_by_address_with_status(self, address, limit):
            return {
                "records": [
                    {
                        "timestamp": 1_002,
                        "slot": 10,
                        "feePayer": "wallet_a",
                        "bundle_value": 100.0,
                        "success": True,
                        "funder": "funder_alpha",
                    },
                    {
                        "timestamp": 1_002,
                        "slot": 10,
                        "feePayer": "wallet_b",
                        "bundle_value": 50.0,
                        "success": False,
                        "funder": "funder_alpha",
                    },
                ],
                "tx_batch_status": "usable",
                "tx_batch_warning": "upstream_failed_use_stale",
                "tx_batch_freshness": "stale_cache_allowed",
                "tx_batch_origin": "fixture_stale_bundle",
                "tx_batch_record_count": 2,
                "tx_fetch_mode": "upstream_failed_use_stale",
                "tx_lake_events": [],
            }

    monkeypatch.setattr(bundle_detector, "collect_bundle_evidence_for_pair", lambda pair, now_ts, settings: {"bundle_evidence_status": "partial"})
    monkeypatch.setattr(
        bundle_detector,
        "compute_bundle_metrics_from_evidence",
        lambda evidence, pair=None: {
            "bundle_count_first_60s": None,
            "bundle_size_value": None,
            "unique_wallets_per_bundle_avg": None,
            "bundle_timing_from_liquidity_add_min": None,
            "bundle_success_rate": None,
            "bundle_enrichment_status": "partial",
            "bundle_enrichment_warning": "real bundle evidence sparse",
            "bundle_evidence_status": "partial",
            "bundle_evidence_source": "fixture",
            "bundle_evidence_warning": "real bundle evidence sparse",
            "bundle_evidence_confidence": 0.4,
            "bundle_metric_origin": "missing",
        },
    )
    monkeypatch.setattr(
        bundle_detector,
        "compute_wallet_clustering_metrics",
        lambda *args, **kwargs: {
            "cluster_concentration_ratio": 0.5,
            "num_unique_clusters_first_60s": 1,
            "bundle_wallet_clustering_score": 0.4,
            "creator_in_cluster_flag": None,
            "shared_funder_link_score": 1.0,
            "linkage_status": "ok",
        },
    )
    monkeypatch.setattr(bundle_detector, "HeliusClient", DummyHelius)
    monkeypatch.setattr(bundle_detector, "acquire", lambda *_args, **_kwargs: None)

    pair = {"pair_created_at_ts": 1_000, "pair_address": "pair-1", "token_address": "mint-1"}
    result = detect_bundle_metrics_for_pair(pair, now_ts=1_120, settings=ProvenanceSettings())

    assert result["bundle_metric_origin"] == "heuristic_fallback"
    assert result["bundle_count_first_60s"] == 1
    assert result["bundle_size_value"] == 150.0
    assert result["bundle_enrichment_status"] == "partial"
    assert "upstream_failed_use_stale" in result["bundle_enrichment_warning"]
    assert "upstream_failed_use_stale" in result["bundle_evidence_warning"]
