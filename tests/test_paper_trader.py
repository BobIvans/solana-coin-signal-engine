import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading.paper_trader import process_entry_signals, process_exit_signals
from trading.position_book import ensure_state


class S:
    PAPER_STARTING_CAPITAL_SOL = 0.1
    PAPER_CONTRACT_VERSION = "paper_trader_v1"
    PAPER_MAX_CONCURRENT_POSITIONS = 3
    PAPER_DEFAULT_SLIPPAGE_BPS = 150
    PAPER_MAX_SLIPPAGE_BPS = 1200
    PAPER_SLIPPAGE_LIQUIDITY_SENSITIVITY = 1.0
    PAPER_PRIORITY_FEE_BASE_SOL = 0.00002
    PAPER_FAILED_TX_BASE_PROB = 0.0
    PAPER_FAILED_TX_LOW_LIQUIDITY_ADDON = 0.0
    PAPER_FAILED_TX_HIGH_VOLATILITY_ADDON = 0.0
    PAPER_PARTIAL_FILL_ALLOWED = True
    PAPER_PARTIAL_FILL_MIN_RATIO = 0.5


def test_exit_then_entry_order(tmp_path: Path):
    state = {"paths": {"signals": tmp_path / "signals.jsonl", "trades": tmp_path / "trades.jsonl"}}
    ensure_state(state, S())

    process_entry_signals(
        [{"token_address": "So1", "symbol": "EX", "entry_decision": "SCALP", "entry_confidence": 0.8, "recommended_position_pct": 0.5, "base_position_pct": 0.5, "effective_position_pct": 0.5, "sizing_multiplier": 1.0, "sizing_origin": "evidence_weighted", "sizing_reason_codes": ["evidence_support_preserved_base_size"], "sizing_confidence": 0.8, "evidence_quality_score": 0.8, "evidence_conflict_flag": False, "partial_evidence_flag": False, "entry_reason": "ok", "entry_snapshot": {}, "contract_version": "paper_trader_v1"}],
        [{"token_address": "So1", "price_usd": 1.0, "liquidity_usd": 1_000_000}],
        state,
        S(),
    )
    pos_id = state["positions"][0]["position_id"]
    process_exit_signals(
        [{"position_id": pos_id, "token_address": "So1", "exit_decision": "FULL_EXIT", "exit_fraction": 1.0, "exit_reason": "done"}],
        [{"token_address": "So1", "price_usd": 1.2, "liquidity_usd": 1_000_000}],
        state,
        S(),
    )
    assert state["positions"][0]["remaining_size_sol"] < state["positions"][0]["position_size_sol"]


def test_entry_execution_and_position_follow_effective_position_pct(tmp_path: Path):
    state = {"paths": {"signals": tmp_path / "signals.jsonl", "trades": tmp_path / "trades.jsonl"}}
    ensure_state(state, S())

    process_entry_signals(
        [{
            "token_address": "So2",
            "symbol": "EF",
            "entry_decision": "SCALP",
            "entry_confidence": 0.8,
            "recommended_position_pct": 0.5,
            "base_position_pct": 0.5,
            "effective_position_pct": 0.2,
            "sizing_multiplier": 0.4,
            "sizing_origin": "risk_reduced",
            "sizing_reason_codes": ["creator_link_risk_size_reduced"],
            "sizing_confidence": 0.62,
            "evidence_quality_score": 0.64,
            "evidence_conflict_flag": True,
            "partial_evidence_flag": False,
            "entry_reason": "risk_reduced",
            "entry_snapshot": {},
            "contract_version": "paper_trader_v1",
        }],
        [{"token_address": "So2", "price_usd": 1.0, "liquidity_usd": 1_000_000}],
        state,
        S(),
    )

    position = state["positions"][0]
    assert position["effective_position_pct"] == 0.2
    assert position["position_size_sol"] <= 0.02 + 1e-9

    trade_row = json.loads((tmp_path / "trades.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert trade_row["effective_position_pct"] == 0.2
    assert trade_row["requested_notional_sol"] <= 0.02 + 1e-9
