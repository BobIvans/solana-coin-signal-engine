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


def test_half_exit_consumes_only_half_cost_basis():
    out = compute_exit_pnl(
        {"remaining_size_sol": 10.0},
        {"filled_notional_sol": 5.0, "requested_notional_sol": 5.0, "priority_fee_sol": 0.0},
    )
    assert out["cost_basis_consumed_sol"] == 5.0
    assert out["closed_fraction_of_position"] == 0.5
    assert out["realized_pnl_sol"] == 0.0


def test_partial_fill_of_partial_exit_consumes_only_filled_fraction():
    out = compute_exit_pnl(
        {"remaining_size_sol": 10.0},
        {"filled_notional_sol": 2.5, "requested_notional_sol": 5.0, "priority_fee_sol": 0.0},
    )
    assert out["cost_basis_consumed_sol"] == 2.5
    assert out["closed_fraction_of_position"] == 0.25
    assert out["realized_pnl_sol"] == 0.0


def test_full_exit_consumes_full_remaining_cost_basis():
    out = compute_exit_pnl(
        {"remaining_size_sol": 10.0},
        {"filled_notional_sol": 10.0, "requested_notional_sol": 10.0, "priority_fee_sol": 0.0},
    )
    assert out["cost_basis_consumed_sol"] == 10.0
    assert out["closed_fraction_of_position"] == 1.0


def test_compute_unrealized_pnl():
    out = compute_unrealized_pnl({"remaining_size_sol": 0.01, "entry_price_usd": 1.0}, {"price_usd": 1.1})
    assert out["unrealized_pnl_sol"] > 0
