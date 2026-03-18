"""Exit snapshot builder for downstream PnL attribution."""

from __future__ import annotations

from typing import Any

from trading.position_monitor import compute_position_deltas
from utils.bundle_contract_fields import BUNDLE_CONTRACT_FIELDS


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_exit_snapshot(position_ctx: dict, current_ctx: dict) -> dict:
    entry_snapshot = dict(position_ctx.get("entry_snapshot") or {})
    deltas = compute_position_deltas(entry_snapshot, current_ctx)

    snapshot = {
        "price_usd": _to_float(current_ctx.get("price_usd_now", current_ctx.get("price_usd"))),
        "buy_pressure_now": _to_float(current_ctx.get("buy_pressure_now", current_ctx.get("buy_pressure"))),
        "volume_velocity_now": _to_float(current_ctx.get("volume_velocity_now", current_ctx.get("volume_velocity"))),
        "liquidity_usd_now": _to_float(current_ctx.get("liquidity_usd_now", current_ctx.get("liquidity_usd"))),
        "liquidity_drop_pct": float(deltas["liquidity_drop_pct"]),
        "x_validation_score_now": _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score"))),
        "x_status_now": str(current_ctx.get("x_status_now", current_ctx.get("x_status") or "unknown")),
        "bundle_cluster_score_now": _to_float(current_ctx.get("bundle_cluster_score_now", current_ctx.get("bundle_cluster_score"))),
        "bundle_cluster_delta": float(deltas["bundle_cluster_delta"]),
        "dev_sell_pressure_now": _to_float(current_ctx.get("dev_sell_pressure_now", current_ctx.get("dev_sell_pressure_5m"))),
        "rug_flag_now": bool(current_ctx.get("rug_flag_now", False)),
    }

    for field in BUNDLE_CONTRACT_FIELDS:
        if field in current_ctx:
            snapshot[field] = current_ctx.get(field)
        elif field in entry_snapshot:
            snapshot[field] = entry_snapshot.get(field)

    for optional_field in ("holder_growth_now", "smart_wallet_hits_now", "market_cap_now"):
        if optional_field in current_ctx and current_ctx.get(optional_field) is not None:
            snapshot[optional_field] = current_ctx.get(optional_field)

    return snapshot
