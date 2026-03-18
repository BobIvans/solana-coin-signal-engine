import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
            },
            {
                "timestamp": 1_002,
                "slot": 10,
                "feePayer": "wallet_b",
                "bundle_value": 50.0,
                "success": False,
            },
            {
                "timestamp": 1_030,
                "slot": 20,
                "feePayer": "wallet_c",
                "bundle_value": 25.0,
                "success": True,
            },
            {
                "timestamp": 1_030,
                "slot": 20,
                "feePayer": "wallet_d",
                "bundle_value": 75.0,
                "success": True,
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


def test_detect_bundle_metrics_is_honest_when_anchor_missing():
    result = detect_bundle_metrics_for_pair({}, now_ts=1_000, settings=DummySettings())

    assert result == safe_null_bundle_metrics(status="unavailable", warning="missing liquidity/pair creation anchor")
