import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.bundle_detector import detect_bundle_metrics_for_pair
from collectors.discovery_engine import run_discovery_once


class DummySettings:
    BUNDLE_ENRICHMENT_ENABLED = True
    BUNDLE_ENRICHMENT_WINDOW_SEC = 60
    BUNDLE_EVIDENCE_ENABLED = True
    BUNDLE_EVIDENCE_MAX_RECORDS = 200
    BUNDLE_EVIDENCE_WINDOW_SEC = 60
    BUNDLE_EVIDENCE_SOURCE_ORDER = "inline,activity,events,flows,attempts"
    HELIUS_API_KEY = ""
    HELIUS_TX_ADDR_LIMIT = 40


def test_sparse_evidence_requires_heuristic_fallback():
    pair = {
        "pair_created_at_ts": 1_000,
        "pair_address": "pair-1",
        "token_address": "token-1",
        "bundle_activity": [
            {"record_id": "r1", "wallet": "w1", "status": "landed", "timestamp": 1_003, "slot": 100, "bundle_value": 100.0},
        ],
        "bundle_transactions": [
            {"timestamp": 1_004, "slot": 10, "feePayer": "wallet_a", "bundle_value": 100.0, "success": True},
            {"timestamp": 1_004, "slot": 10, "feePayer": "wallet_b", "bundle_value": 50.0, "success": True},
            {"timestamp": 1_020, "slot": 11, "feePayer": "wallet_c", "bundle_value": 25.0, "success": False},
            {"timestamp": 1_020, "slot": 11, "feePayer": "wallet_d", "bundle_value": 75.0, "success": True},
        ],
    }

    result = detect_bundle_metrics_for_pair(pair, now_ts=1_040, settings=DummySettings())

    assert result["bundle_metric_origin"] == "heuristic_fallback"
    assert result["bundle_evidence_status"] in {"partial", "ok"}
    assert result["bundle_count_first_60s"] == 2
    assert result["bundle_enrichment_status"] == "ok"


def test_discovery_status_reports_real_fallback_and_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("SMOKE_DIR", str(tmp_path / "smoke"))
    monkeypatch.setenv("X_MAX_TOKENS_PER_CYCLE", "5")
    monkeypatch.setattr("collectors.discovery_engine.utc_now_ts", lambda: 1_000)
    monkeypatch.setattr("collectors.discovery_engine.utc_now_iso", lambda: "2026-03-19T00:00:00Z")

    raw_pairs = [
        {
            "pairAddress": "pair_real",
            "chainId": "solana",
            "dexId": "raydium",
            "pairCreatedAt": 700,
            "baseToken": {"address": "tok_real", "symbol": "REAL", "name": "Real"},
            "priceUsd": "0.1",
            "fdv": 300000,
            "marketCap": 0,
            "liquidity": {"usd": 25000},
            "volume": {"m5": 10000, "h1": 12000},
            "txns": {"m5": {"buys": 15, "sells": 10}},
            "bundle_activity": [
                {"group_id": "g1", "wallet": "w1", "status": "landed", "timestamp": 705, "slot": 51, "bundle_value": 100.0},
                {"group_id": "g1", "wallet": "w2", "status": "landed", "timestamp": 706, "slot": 51, "bundle_value": 50.0},
            ],
        },
        {
            "pairAddress": "pair_fallback",
            "chainId": "solana",
            "dexId": "raydium",
            "pairCreatedAt": 710,
            "baseToken": {"address": "tok_fallback", "symbol": "FB", "name": "Fallback"},
            "priceUsd": "0.1",
            "fdv": 300000,
            "marketCap": 0,
            "liquidity": {"usd": 25000},
            "volume": {"m5": 10000, "h1": 12000},
            "txns": {"m5": {"buys": 15, "sells": 10}},
            "bundle_activity": [{"wallet": "w1", "status": "landed", "timestamp": 715, "slot": 60, "bundle_value": 100.0}],
            "bundle_transactions": [
                {"timestamp": 715, "slot": 61, "feePayer": "wa", "bundle_value": 20.0, "success": True},
                {"timestamp": 715, "slot": 61, "feePayer": "wb", "bundle_value": 30.0, "success": True},
            ],
        },
        {
            "pairAddress": "pair_missing",
            "chainId": "solana",
            "dexId": "raydium",
            "pairCreatedAt": 720,
            "baseToken": {"address": "tok_missing", "symbol": "MISS", "name": "Missing"},
            "priceUsd": "0.1",
            "fdv": 300000,
            "marketCap": 0,
            "liquidity": {"usd": 25000},
            "volume": {"m5": 10000, "h1": 12000},
            "txns": {"m5": {"buys": 15, "sells": 10}},
        },
    ]

    monkeypatch.setattr("collectors.discovery_engine.fetch_latest_solana_pairs", lambda: raw_pairs)
    result = run_discovery_once()
    status = result["status"]["bundle_enrichment"]

    assert status["origin_counts"]["real_evidence"] == 1
    assert status["origin_counts"]["heuristic_fallback"] == 1
    assert status["origin_counts"]["missing"] == 1
