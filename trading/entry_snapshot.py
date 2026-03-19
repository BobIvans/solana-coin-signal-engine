"""Snapshot builder for downstream paper/exit engines."""

from __future__ import annotations

from typing import Any

from utils.bundle_contract_fields import BUNDLE_CONTRACT_FIELDS
from utils.short_horizon_contract_fields import SHORT_HORIZON_SIGNAL_FIELDS

_ENTRY_SNAPSHOT_FIELDS = [
    "final_score",
    "regime_candidate",
    "age_sec",
    "price_usd",
    "buy_pressure",
    "volume_velocity",
    "liquidity_growth",
    "first30s_buy_ratio",
    "bundle_cluster_score",
    "x_validation_score",
    "x_validation_delta",
    "x_status",
    "holder_growth_5m",
    "smart_wallet_hits",
    "dev_sell_pressure_5m",
    "rug_score",
    *BUNDLE_CONTRACT_FIELDS,
    *SHORT_HORIZON_SIGNAL_FIELDS,
]


def build_entry_snapshot(token_ctx: dict[str, Any]) -> dict[str, Any]:
    return {field: token_ctx.get(field) for field in _ENTRY_SNAPSHOT_FIELDS}
