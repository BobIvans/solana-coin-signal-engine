import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.discovery_engine import build_shortlist, filter_pair, run_discovery_once
from utils.bundle_contract_fields import BUNDLE_CONTRACT_FIELDS


def _sample_pair(**overrides):
    base = {
        "chain": "solana",
        "pair_created_at_ts": 700,
        "liquidity_usd": 25_000,
        "fdv": 300_000,
        "market_cap": 0,
        "txns_m5_buys": 15,
        "txns_m5_sells": 10,
        "paid_order_flag": False,
    }
    base.update(overrides)
    return base


def _raw_pair(**overrides):
    base = {
        "chainId": "solana",
        "pairAddress": "pair_1",
        "pairCreatedAt": 700_000,
        "baseToken": {"address": "tok_1", "symbol": "TOK", "name": "Token"},
        "liquidity": {"usd": 25_000},
        "fdv": 300_000,
        "marketCap": 0,
        "txns": {"m5": {"buys": 15, "sells": 10}},
        "volume": {"m5": 125_000, "h1": 125_000},
        "boosts": {"active": False},
        "info": {"paid": False},
    }
    base.update(overrides)
    return base


@pytest.fixture
def discovery_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("SMOKE_DIR", str(tmp_path / "smoke"))
    monkeypatch.setenv("X_MAX_TOKENS_PER_CYCLE", "5")
    monkeypatch.setattr("collectors.discovery_engine.utc_now_ts", lambda: 1_000)
    monkeypatch.setattr("collectors.discovery_engine.utc_now_iso", lambda: "1970-01-01T00:16:40Z")
    return tmp_path


def test_filter_pair_accepts_fresh_liquid_pair():
    accepted, reason = filter_pair(_sample_pair(), now_ts=1_000)
    assert accepted is True
    assert reason == "ok"


def test_filter_pair_rejects_old_pair():
    accepted, reason = filter_pair(_sample_pair(pair_created_at_ts=200), now_ts=1_000)
    assert accepted is False
    assert reason == "age_too_high"


def test_filter_pair_rejects_paid_order():
    accepted, reason = filter_pair(_sample_pair(paid_order_flag=True), now_ts=1_000)
    assert accepted is False
    assert reason == "paid_order"


def test_shortlist_sorted_by_fast_prescore_desc():
    candidates = [
        {"pair_address": "2", "fast_prescore": 55, "volume_m5": 100, "token_address": "t2"},
        {"pair_address": "1", "fast_prescore": 88, "volume_m5": 80, "token_address": "t1"},
        {"pair_address": "3", "fast_prescore": 72, "volume_m5": 90, "token_address": "t3"},
    ]

    shortlist = build_shortlist(candidates, top_k=2)

    assert [item["pair_address"] for item in shortlist] == ["1", "3"]


def test_discovery_smoke_with_bundle_enrichment_disabled(monkeypatch, discovery_tmp):
    monkeypatch.setenv("BUNDLE_ENRICHMENT_ENABLED", "false")
    monkeypatch.setattr("collectors.discovery_engine.fetch_latest_solana_pairs", lambda: [_raw_pair()])

    result = run_discovery_once()

    candidate = result["candidates"]["candidates"][0]
    shortlist_item = result["shortlist"]["shortlist"][0]
    for field in BUNDLE_CONTRACT_FIELDS[:5]:
        assert field in candidate
        assert field in shortlist_item
        assert candidate[field] is None
        assert shortlist_item[field] is None
    assert candidate["bundle_enrichment_status"] == "disabled"
    status_path = discovery_tmp / "smoke" / "discovery_status.json"
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["bundle_enrichment"]["enabled"] is False


def test_discovery_smoke_with_bundle_enrichment_enabled_and_mocked_metrics(monkeypatch, discovery_tmp):
    monkeypatch.setenv("BUNDLE_ENRICHMENT_ENABLED", "true")
    monkeypatch.setattr("collectors.discovery_engine.fetch_latest_solana_pairs", lambda: [_raw_pair()])
    monkeypatch.setattr(
        "collectors.discovery_engine.detect_bundle_metrics_for_pair",
        lambda pair, now_ts, settings: {
            "bundle_count_first_60s": 2,
            "bundle_size_value": 123.4,
            "unique_wallets_per_bundle_avg": 2.5,
            "bundle_timing_from_liquidity_add_min": 0.25,
            "bundle_success_rate": 0.8,
            "bundle_enrichment_status": "ok",
            "bundle_enrichment_warning": None,
            **{field: None for field in BUNDLE_CONTRACT_FIELDS[5:]},
        },
    )

    result = run_discovery_once()

    candidate = result["candidates"]["candidates"][0]
    shortlist_item = result["shortlist"]["shortlist"][0]
    assert candidate["fast_prescore"] == pytest.approx(shortlist_item["fast_prescore"])
    assert candidate["bundle_count_first_60s"] == 2
    assert shortlist_item["bundle_size_value"] == 123.4
    assert shortlist_item["unique_wallets_per_bundle_avg"] == 2.5
    assert shortlist_item["bundle_timing_from_liquidity_add_min"] == 0.25
    assert shortlist_item["bundle_success_rate"] == 0.8


def test_discovery_bundle_enrichment_failure_keeps_candidate(monkeypatch, discovery_tmp):
    monkeypatch.setenv("BUNDLE_ENRICHMENT_ENABLED", "true")
    monkeypatch.setattr("collectors.discovery_engine.fetch_latest_solana_pairs", lambda: [_raw_pair()])

    def _boom(*args, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr("collectors.discovery_engine.detect_bundle_metrics_for_pair", _boom)

    result = run_discovery_once()

    candidate = result["candidates"]["candidates"][0]
    shortlist_item = result["shortlist"]["shortlist"][0]
    assert candidate["token_address"] == "tok_1"
    assert candidate["bundle_enrichment_status"] == "failed"
    assert candidate["bundle_enrichment_warning"] == "rate limited"
    for field in BUNDLE_CONTRACT_FIELDS[:5]:
        assert candidate[field] is None
        assert shortlist_item[field] is None
