import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.position_book import apply_partial_exit, ensure_state, open_position


class S:
    PAPER_STARTING_CAPITAL_SOL = 20.0
    PAPER_CONTRACT_VERSION = "paper_trader_v1"


def test_open_and_partial_exit_flow():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 0.01, "priority_fee_sol": 0.00002},
        {"token_address": "So1", "symbol": "EX", "entry_decision": "SCALP", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )
    apply_partial_exit(pos, {"filled_notional_sol": 0.005, "requested_notional_sol": 0.005, "executed_price_usd": 1.1, "priority_fee_sol": 0.00001}, state)
    assert pos["remaining_size_sol"] < pos["position_size_sol"]


def test_half_exit_keeps_half_remaining_capital_in_position():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "priority_fee_sol": 0.0},
        {"token_address": "SoHalf", "symbol": "HALF", "entry_decision": "SCALP", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )

    apply_partial_exit(
        pos,
        {"filled_notional_sol": 5.0, "requested_notional_sol": 5.0, "executed_price_usd": 1.0, "priority_fee_sol": 0.0},
        state,
    )

    assert pos["remaining_size_sol"] == 5.0
    assert state["portfolio"]["capital_in_positions_sol"] == 5.0
    assert pos["realized_pnl_sol"] == 0.0


def test_partial_fill_consumes_only_closed_cost_portion():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "priority_fee_sol": 0.0},
        {"token_address": "SoQuarter", "symbol": "QTR", "entry_decision": "SCALP", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )

    apply_partial_exit(
        pos,
        {"filled_notional_sol": 2.5, "requested_notional_sol": 5.0, "executed_price_usd": 1.0, "priority_fee_sol": 0.0},
        state,
    )

    assert pos["remaining_size_sol"] == 7.5
    assert state["portfolio"]["capital_in_positions_sol"] == 7.5
    assert pos["realized_pnl_sol"] == 0.0
