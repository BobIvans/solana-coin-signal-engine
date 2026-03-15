"""Core JSON contracts for PR-1 bootstrap artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TokenCandidate:
    token_address: str
    pair_address: str
    symbol: str
    name: str
    chain: str = "solana"
    discovered_at_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalRecord:
    token_address: str
    timestamp_utc: str
    stage: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeRecord:
    token_address: str
    entry_time_utc: str
    exit_time_utc: str
    regime: str
    pnl_pct: float
    exit_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionRecord:
    token_address: str
    status: str = "open"
    entry_price: float = 0.0
    entry_time_utc: str = ""
    entry_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
