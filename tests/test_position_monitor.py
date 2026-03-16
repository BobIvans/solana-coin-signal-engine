import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.position_monitor import compute_hold_sec, compute_pnl_pct, compute_position_deltas


def test_compute_hold_sec_utc_iso():
    assert compute_hold_sec("2026-03-15T12:30:41Z", "2026-03-15T12:31:04Z") == 23


def test_compute_pnl_pct():
    assert round(compute_pnl_pct(1.0, 1.124), 2) == 12.40


def test_compute_position_deltas():
    deltas = compute_position_deltas(
        {"volume_velocity": 4.8, "bundle_cluster_score": 0.66, "x_validation_score": 71.4, "liquidity_usd": 30000},
        {"volume_velocity_now": 3.1, "bundle_cluster_score_now": 0.41, "x_validation_score_now": 49.0, "liquidity_usd_now": 23700},
    )
    assert round(deltas["liquidity_drop_pct"], 1) == 21.0
    assert round(deltas["bundle_cluster_delta"], 2) == -0.25
    assert round(deltas["volume_velocity_ratio_vs_entry"], 4) == 0.6458
