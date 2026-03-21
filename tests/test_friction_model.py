import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.friction_model import (
    compute_failed_tx_probability,
    compute_partial_fill_ratio,
    compute_priority_fee_sol,
    compute_slippage_bps,
)


class S:
    PAPER_DEFAULT_SLIPPAGE_BPS = 150
    PAPER_MAX_SLIPPAGE_BPS = 1200
    PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY = 1.0
    PAPER_PRIORITY_FEE_BASE_SOL = 0.00002
    PAPER_FAILED_TX_BASE_PROB = 0.03
    PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON = 0.05
    PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON = 0.04
    PAPER_PARTIAL_FILL_ALLOWED = True
    PAPER_PARTIAL_FILL_MIN_RATIO = 0.5
    PAPER_SOL_USD_FALLBACK = 88.0


def test_slippage_clamped():
    bps = compute_slippage_bps({"requested_notional_sol": 1.0}, {"liquidity_usd": 1000, "volatility": 3.0}, S())
    assert 1 <= bps <= S.PAPER_MAX_SLIPPAGE_BPS


def test_priority_fee_base():
    fee = compute_priority_fee_sol({}, {}, S())
    assert fee == S.PAPER_PRIORITY_FEE_BASE_SOL


def test_failed_tx_probability_bounds():
    prob = compute_failed_tx_probability({"entry_confidence": 0.4}, {"liquidity_usd": 1000, "volatility": 4}, S())
    assert 0 <= prob <= 1


def test_partial_fill_ratio_bounds():
    ratio = compute_partial_fill_ratio({"requested_notional_sol": 1}, {"liquidity_usd": 1000, "volatility": 3}, S())
    assert S.PAPER_PARTIAL_FILL_MIN_RATIO <= ratio <= 1.0


def test_sol_usd_uses_settings_fallback_instead_of_hardcoded_100():
    bps = compute_slippage_bps({"requested_notional_sol": 1.0}, {"liquidity_usd": 1000, "volatility": 0.0}, S())
    ratio = compute_partial_fill_ratio({"requested_notional_sol": 1.0}, {"liquidity_usd": 1000, "volatility": 0.0}, S())
    assert bps < S.PAPER_MAX_SLIPPAGE_BPS
    assert ratio > S.PAPER_PARTIAL_FILL_MIN_RATIO
