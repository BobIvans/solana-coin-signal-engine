import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.discovery_engine import build_shortlist, filter_pair


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
