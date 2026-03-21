import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.friction_model import (
    compute_failed_tx_probability,
    compute_fill_realism,
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
    FRICTION_MODEL_MODE = "amm_approx"
    PAPER_AMM_IMPACT_EXPONENT = 1.35
    CONGESTION_STRESS_ENABLED = True
    FRICTION_THIN_DEPTH_DEX_IDS = "meteora"
    FRICTION_THIN_DEPTH_PAIR_TYPES = "clmm,dlmm"
    FRICTION_THIN_DEPTH_LIQUIDITY_MULTIPLIER = 0.6
    FRICTION_THIN_DEPTH_STRESS_SELL_MULTIPLIER = 0.7
    FRICTION_CATASTROPHIC_LIQUIDITY_RATIO = 1.1
    FRICTION_CATASTROPHIC_FILLED_FRACTION = 0.15
    FRICTION_CATASTROPHIC_SLIPPAGE_BPS = 2500


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


def test_thin_depth_penalty_reduces_effective_liquidity():
    result = compute_fill_realism(
        {"requested_notional_sol": 1.0, "side": "sell"},
        {"liquidity_usd": 10_000, "volatility": 0.2, "dexId": "meteora", "pair_type": "clmm"},
        S(),
    )
    assert result["effective_liquidity_usd"] < 10_000
    assert result["thin_depth_penalty_multiplier"] < 1.0


def test_catastrophic_liquidity_failure_sets_high_severity_fill_status():
    result = compute_fill_realism(
        {"requested_notional_sol": 20.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["cluster_dump_detected"]},
        {"liquidity_usd": 2_000, "volatility": 0.4, "sell_pressure": 0.95},
        S(),
    )
    assert result["fill_status"] == "catastrophic_liquidity_failure"
    assert result["execution_warning"]
    assert result["filled_fraction"] < 0.5


def test_full_exit_with_cluster_dump_is_harsher_than_normal_exit():
    normal = compute_fill_realism(
        {"requested_notional_sol": 2.0, "side": "sell", "exit_decision": "FULL_EXIT"},
        {"liquidity_usd": 20_000, "volatility": 0.2, "sell_pressure": 0.4},
        S(),
    )
    stressed = compute_fill_realism(
        {"requested_notional_sol": 2.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["cluster_dump_detected"]},
        {"liquidity_usd": 5_000, "volatility": 0.2, "sell_pressure": 0.95, "cluster_sell_concentration_120s": 0.95},
        S(),
    )
    assert stressed["effective_slippage_bps"] > normal["effective_slippage_bps"]
