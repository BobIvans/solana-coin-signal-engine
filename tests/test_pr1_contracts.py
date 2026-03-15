import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.json_contracts import PositionRecord, SignalRecord, TokenCandidate, TradeRecord


def test_token_candidate_contract():
    candidate = TokenCandidate(
        token_address="token",
        pair_address="pair",
        symbol="SYM",
        name="Name",
        discovered_at_utc="2026-03-15T12:00:00Z",
    ).to_dict()

    assert {"token_address", "pair_address", "symbol", "name", "chain", "discovered_at_utc"} <= set(candidate)
    assert isinstance(candidate["discovered_at_utc"], str)


def test_signal_trade_position_contracts():
    signal = SignalRecord(
        token_address="token",
        timestamp_utc="2026-03-15T12:00:00Z",
        stage="bootstrap",
        status="ok",
        payload={},
    ).to_dict()
    trade = TradeRecord(
        token_address="token",
        entry_time_utc="2026-03-15T12:00:00Z",
        exit_time_utc="2026-03-15T12:00:01Z",
        regime="SMOKE",
        pnl_pct=0.0,
        exit_reason="bootstrap_check",
    ).to_dict()
    position = PositionRecord(
        token_address="token",
        entry_time_utc="2026-03-15T12:00:00Z",
        entry_price=0.0,
    ).to_dict()

    assert isinstance(signal["timestamp_utc"], str)
    assert isinstance(trade["entry_time_utc"], str)
    assert isinstance(trade["pnl_pct"], float)
    assert isinstance(position["entry_price"], float)
