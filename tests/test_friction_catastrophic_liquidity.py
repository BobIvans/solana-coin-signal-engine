import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.friction_model import compute_fill_realism


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
    PAPER_SOL_USD_FALLBACK = 100.0
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


def test_effective_liquidity_is_lower_for_thin_depth_pool():
    result = compute_fill_realism(
        {"requested_notional_sol": 1.0, "side": "sell"},
        {"liquidity_usd": 10_000, "volatility": 0.2, "dexId": "meteora", "pair_type": "clmm"},
        S(),
    )
    assert result["effective_liquidity_usd"] < 10_000


def test_catastrophic_exit_path_sets_fill_status_warning():
    result = compute_fill_realism(
        {"requested_notional_sol": 20.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["kill_switch_triggered"]},
        {"liquidity_usd": 2_000, "volatility": 0.3, "sell_pressure": 0.97, "cluster_sell_concentration_120s": 0.97},
        S(),
    )
    assert result["fill_status"] == "catastrophic_liquidity_failure"
    assert result["execution_warning"]


def test_catastrophic_path_is_harsher_than_regular_high_slippage_path():
    regular = compute_fill_realism(
        {"requested_notional_sol": 2.0, "side": "sell", "exit_decision": "FULL_EXIT"},
        {"liquidity_usd": 12_000, "volatility": 0.2, "sell_pressure": 0.5},
        S(),
    )
    catastrophic = compute_fill_realism(
        {"requested_notional_sol": 20.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["cluster_dump_detected"]},
        {"liquidity_usd": 2_000, "volatility": 0.3, "sell_pressure": 0.97, "cluster_sell_concentration_120s": 0.97},
        S(),
    )
    assert catastrophic["effective_slippage_bps"] > regular["effective_slippage_bps"]
    assert catastrophic["filled_fraction"] < regular["filled_fraction"]
