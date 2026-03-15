import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.fill_model import simulate_entry_fill, simulate_exit_fill


class S:
    PAPER_DEFAULT_SLIPPAGE_BPS = 150
    PAPER_MAX_SLIPPAGE_BPS = 1200
    PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY = 1.0
    PAPER_PRIORITY_FEE_BASE_SOL = 0.00002
    PAPER_FAILED_TX_BASE_PROB = 0.0
    PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON = 0.0
    PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON = 0.0
    PAPER_PARTIAL_FILL_ALLOWED = True
    PAPER_PARTIAL_FILL_MIN_RATIO = 0.5


def test_simulate_entry_fill_success():
    fill = simulate_entry_fill(
        {"token_address": "So1", "recommended_position_pct": 0.5, "entry_confidence": 0.8},
        {"price_usd": 1.0, "liquidity_usd": 1_000_000, "volatility": 0.1},
        {"free_capital_sol": 0.1},
        S(),
    )
    assert fill["tx_failed"] is False
    assert 0 < fill["fill_ratio"] <= 1


def test_simulate_exit_fill_success():
    fill = simulate_exit_fill(
        {"position_id": "pos_0001", "remaining_size_sol": 0.05, "entry_price_usd": 1.0},
        {"exit_decision": "FULL_EXIT", "exit_fraction": 1.0, "signal_quality": 1.0},
        {"price_usd": 1.2, "liquidity_usd": 1_000_000, "volatility": 0.1},
        S(),
    )
    assert fill["tx_failed"] is False
    assert fill["filled_notional_sol"] > 0
