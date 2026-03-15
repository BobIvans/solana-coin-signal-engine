import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.fast_prescore import compute_buy_pressure, compute_fast_prescore, compute_volume_mcap_ratio


def test_buy_pressure_calculation():
    pair = {"txns_m5_buys": 30, "txns_m5_sells": 10}
    assert compute_buy_pressure(pair) == 0.75


def test_volume_mcap_ratio_uses_market_cap_first():
    pair = {"volume_m5": 1_000, "market_cap": 20_000, "fdv": 100_000}
    assert compute_volume_mcap_ratio(pair) == 0.05


def test_fast_prescore_in_range_and_boost_penalty_applied():
    now_ts = 1_800
    base = {
        "pair_created_at_ts": 1_400,
        "volume_m5": 10_000,
        "market_cap": 100_000,
        "fdv": 100_000,
        "txns_m5_buys": 30,
        "txns_m5_sells": 10,
        "liquidity_usd": 40_000,
        "boost_flag": False,
        "paid_order_flag": False,
    }

    no_boost = compute_fast_prescore(base, now_ts)
    with_boost = compute_fast_prescore({**base, "boost_flag": True}, now_ts)

    assert 0 <= no_boost["fast_prescore"] <= 100
    assert with_boost["fast_prescore"] < no_boost["fast_prescore"]
