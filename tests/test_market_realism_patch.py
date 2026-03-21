from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.continuation_enricher import compute_continuation_metrics
from collectors.dexscreener_client import classify_discovery_honesty, normalize_pair
from collectors.helius_client import assess_tx_window_coverage
from collectors.solana_rpc_client import TOKEN_PROGRAM_2022, summarize_token_program_safety
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


PAIR_CREATED_TS = 1_000


def _organic_txs() -> list[dict]:
    return [
        {
            "timestamp": 1_000,
            "success": True,
            "liquidity_usd": 100.0,
            "participants": [{"wallet": "buyer_a"}, {"wallet": "buyer_b"}],
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 6},
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_b", "tokenAmount": 6},
            ],
        },
        {
            "timestamp": 1_025,
            "success": True,
            "liquidity_usd": 60.0,
            "tokenTransfers": [
                {"fromUserAccount": "buyer_a", "toUserAccount": "lp_pool", "tokenAmount": 18},
            ],
        },
        {
            "timestamp": 1_050,
            "success": True,
            "liquidity_usd": 100.0,
            "tokenTransfers": [
                {"fromUserAccount": "lp_pool", "toUserAccount": "buyer_a", "tokenAmount": 4},
            ],
        },
    ]


def test_discovery_lag_classification_marks_delayed_launch_window():
    out = classify_discovery_honesty(pair_created_at_ts=1_000, discovery_seen_ts=1_121)
    assert out["discovery_lag_sec"] == 121
    assert out["delayed_launch_window_flag"] is True
    assert out["first_window_native_visibility"] is False
    assert out["discovery_freshness_status"] == "post_first_window"



def test_native_vs_post_first_window_labeling():
    early = classify_discovery_honesty(pair_created_at_ts=1_000, discovery_seen_ts=1_005)
    late = classify_discovery_honesty(pair_created_at_ts=1_000, discovery_seen_ts=1_080)
    assert early["discovery_freshness_status"] == "native_first_window"
    assert late["discovery_freshness_status"] == "post_first_window"



def test_normalize_pair_includes_discovery_honesty_fields():
    row = normalize_pair(
        {
            "chainId": "solana",
            "pairAddress": "pair_1",
            "pairCreatedAt": 1_000,
            "baseToken": {"address": "tok_1", "symbol": "TOK", "name": "Token"},
        },
        discovery_seen_ts=1_080,
    )
    assert "discovery_lag_sec" in row
    assert row["discovery_freshness_status"] == "post_first_window"



def test_tx_first_window_coverage_complete():
    txs = [{"timestamp": 995, "signature": "sig_1"}, {"timestamp": 1_010, "signature": "sig_2"}]
    out = assess_tx_window_coverage(txs, pair_created_ts=1_000, fetch_depth=2, fetch_pages=1)
    assert out["tx_first_window_coverage_ratio"] == 1.0
    assert out["tx_window_truncation_flag"] is False
    assert out["tx_window_status"] == "complete_first_window"



def test_tx_first_window_truncation_honesty():
    txs = [{"timestamp": 1_040, "signature": "sig_2"}, {"timestamp": 1_050, "signature": "sig_3"}]
    out = assess_tx_window_coverage(txs, pair_created_ts=1_000, fetch_depth=2, fetch_pages=1)
    assert out["tx_first_window_coverage_ratio"] < 1.0
    assert out["tx_window_status"] in {"truncated_first_window", "partial_first_window"}
    assert out["tx_window_warning"]



def test_continuation_confidence_degraded_by_partial_tx_window():
    result = compute_continuation_metrics(
        token_ctx={
            "pair_created_at": "1970-01-01T00:16:40Z",
            "tx_window_status": "truncated_first_window",
            "tx_first_window_coverage_ratio": 0.4,
            "tx_window_warning": "tx_window_truncated_by_fetch_depth",
        },
        txs=_organic_txs(),
        pair_created_ts=PAIR_CREATED_TS,
    )
    assert result["continuation_coverage_ratio"] < 1.0
    assert result["continuation_inputs_status"]["tx"] == "partial"
    assert any("tx_window" in warning for warning in result["continuation_warnings"])



def test_amm_aware_slippage_grows_non_linearly_and_partial_exit_is_cheaper():
    settings = S()
    market_ctx = {"liquidity_usd": 10_000, "volatility": 0.1, "sell_pressure": 0.6}
    small = compute_fill_realism({"requested_notional_sol": 0.1, "side": "sell"}, market_ctx, settings)
    large = compute_fill_realism({"requested_notional_sol": 2.0, "side": "sell"}, market_ctx, settings)
    partial = compute_fill_realism({"requested_notional_sol": 0.5, "side": "sell", "exit_decision": "FULL_EXIT"}, market_ctx, settings)
    full = compute_fill_realism({"requested_notional_sol": 2.0, "side": "sell", "exit_decision": "FULL_EXIT"}, market_ctx, settings)
    assert large["estimated_price_impact_bps"] > small["estimated_price_impact_bps"]
    assert full["effective_slippage_bps"] > partial["effective_slippage_bps"]



def test_congestion_stress_on_urgent_exit():
    settings = S()
    market_ctx = {"liquidity_usd": 25_000, "volatility": 0.2}
    normal = compute_fill_realism({"requested_notional_sol": 1.0, "side": "sell", "exit_decision": "FULL_EXIT"}, market_ctx, settings)
    stressed = compute_fill_realism(
        {"requested_notional_sol": 1.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["cluster_dump_detected"]},
        market_ctx,
        settings,
    )
    assert stressed["congestion_stress_multiplier"] > normal["congestion_stress_multiplier"]
    assert stressed["effective_slippage_bps"] > normal["effective_slippage_bps"]



def test_token_2022_detection_and_transfer_fee_risk():
    payload = {
        "owner": TOKEN_PROGRAM_2022,
        "data": {
            "parsed": {
                "info": {
                    "extensions": [
                        {
                            "extension": "transferFeeConfig",
                            "newerTransferFee": {"transferFeeBasisPoints": 450},
                        }
                    ]
                }
            }
        },
    }
    out = summarize_token_program_safety(payload, transfer_fee_sellability_block_bps=300)
    assert out["token_2022_flag"] is True
    assert out["transfer_fee_detected"] is True
    assert out["transfer_fee_bps"] == 450.0
    assert out["sellability_risk_flag"] is True



def test_post_first_window_candidate_cannot_promote_to_trend():
    late = classify_discovery_honesty(pair_created_at_ts=1_000, discovery_seen_ts=1_100)
    assert late["discovery_freshness_status"] == "post_first_window"
    assert late["delayed_launch_window_flag"] is True


def test_quote_token_bundle_value_is_not_underestimated_as_native_only():
    from collectors import bundle_detector

    value, origin = bundle_detector._extract_value(
        {"tokenTransfers": [{"tokenSymbol": "USDC", "tokenAmount": 250.0}]},
        None,
    )
    assert value == 250.0
    assert origin == "quote_transfer"


def test_catastrophic_liquidity_path_is_not_benign_fill():
    result = compute_fill_realism(
        {"requested_notional_sol": 25.0, "side": "sell", "exit_decision": "FULL_EXIT", "exit_flags": ["cluster_dump_detected"]},
        {"liquidity_usd": 2_500, "volatility": 0.4, "sell_pressure": 0.98, "cluster_sell_concentration_120s": 0.98},
        S(),
    )
    assert result["fill_status"] == "catastrophic_liquidity_failure"
    assert result["execution_warning"]
