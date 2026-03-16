import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.pnl_engine import compute_entry_costs, compute_exit_pnl, compute_unrealized_pnl


def test_compute_entry_costs():
    out = compute_entry_costs({"filled_notional_sol": 0.01, "priority_fee_sol": 0.001})
    assert out["fees_paid_sol"] == 0.001


def test_compute_exit_pnl():
    out = compute_exit_pnl(
        {"remaining_size_sol": 0.01},
        {"filled_notional_sol": 0.02, "requested_notional_sol": 0.02, "priority_fee_sol": 0.001},
    )
    assert out["realized_pnl_sol"] > 0


def test_compute_unrealized_pnl():
    out = compute_unrealized_pnl({"remaining_size_sol": 0.01, "entry_price_usd": 1.0}, {"price_usd": 1.1})
    assert out["unrealized_pnl_sol"] > 0
