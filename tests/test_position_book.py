import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.position_book import apply_partial_exit, ensure_state, open_position, release_pending_settlements


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


def test_partial_exit_marks_partial_1_state_once():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "filled_cost_basis_sol": 10.0, "priority_fee_sol": 0.0, "fill_ratio": 1.0},
        {"token_address": "SoP1", "symbol": "P1", "entry_decision": "TREND", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )
    apply_partial_exit(
        pos,
        {"filled_notional_sol": 4.0, "requested_notional_sol": 3.3, "filled_cost_basis_sol": 3.3, "executed_price_usd": 1.2, "priority_fee_sol": 0.0, "exit_flags": ["partial_take_profit_1"]},
        state,
    )
    assert pos["partial_1_taken"] is True
    assert "partial_1" in pos["partials_taken"]


def test_repeated_partial_1_does_not_duplicate_state_marker():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "filled_cost_basis_sol": 10.0, "priority_fee_sol": 0.0, "fill_ratio": 1.0},
        {"token_address": "SoP2", "symbol": "P2", "entry_decision": "TREND", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )
    fill = {"filled_notional_sol": 4.0, "requested_notional_sol": 3.3, "filled_cost_basis_sol": 3.3, "executed_price_usd": 1.2, "priority_fee_sol": 0.0, "exit_flags": ["partial_take_profit_1"]}
    apply_partial_exit(pos, fill, state)
    apply_partial_exit(pos, fill, state)
    assert pos["partials_taken"].count("partial_1") == 1


def test_partial_exit_creates_pending_settlement_instead_of_immediate_free_capital():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "filled_cost_basis_sol": 10.0, "priority_fee_sol": 0.0, "fill_ratio": 1.0},
        {"token_address": "SoSettle1", "symbol": "ST1", "entry_decision": "SCALP", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )
    free_capital_before_exit = state["portfolio"]["free_capital_sol"]

    apply_partial_exit(
        pos,
        {"filled_notional_sol": 4.0, "requested_notional_sol": 4.0, "filled_cost_basis_sol": 4.0, "executed_price_usd": 1.2, "priority_fee_sol": 0.1, "exit_reason": "take_profit"},
        state,
    )

    assert state["portfolio"]["free_capital_sol"] == free_capital_before_exit
    assert state["portfolio"]["pending_settlement_count"] == 1
    assert state["portfolio"]["pending_settlement_sol"] > 0.0


def test_release_pending_settlements_is_idempotent():
    state = {}
    ensure_state(state, S())
    pos = open_position(
        {"executed_price_usd": 1.0, "filled_notional_sol": 10.0, "filled_cost_basis_sol": 10.0, "priority_fee_sol": 0.0, "fill_ratio": 1.0},
        {"token_address": "SoSettle2", "symbol": "ST2", "entry_decision": "SCALP", "entry_snapshot": {}, "contract_version": "paper_trader_v1"},
        state,
    )
    apply_partial_exit(
        pos,
        {"filled_notional_sol": 3.0, "requested_notional_sol": 3.0, "filled_cost_basis_sol": 3.0, "executed_price_usd": 1.1, "priority_fee_sol": 0.0, "exit_reason": "take_profit"},
        state,
    )

    free_capital_before_release = state["portfolio"]["free_capital_sol"]
    state["settlement_cycle_seq"] = 1
    first_release = release_pending_settlements(state)
    free_capital_after_first = state["portfolio"]["free_capital_sol"]
    second_release = release_pending_settlements(state)

    assert first_release["released_count"] == 1
    assert free_capital_after_first > free_capital_before_release
    assert second_release["released_count"] == 0
    assert state["portfolio"]["free_capital_sol"] == free_capital_after_first
    assert state["portfolio"]["pending_settlement_count"] == 0
