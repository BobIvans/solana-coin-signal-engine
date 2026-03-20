"""Position monitoring helpers for exit decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from math import floor
from typing import Any

from config.settings import Settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, write_json


def _parse_utc(ts: str) -> datetime:
    value = str(ts or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_hold_sec(entry_time: str, now_ts: str) -> int:
    entry_dt = _parse_utc(entry_time)
    now_dt = _parse_utc(now_ts)
    return max(0, floor((now_dt - entry_dt).total_seconds()))


def compute_pnl_pct(entry_price: float, current_price: float) -> float:
    entry = float(entry_price)
    current = float(current_price)
    if entry <= 0:
        raise ValueError("entry_price must be > 0")
    return ((current - entry) / entry) * 100.0


def compute_position_deltas(entry_snapshot: dict, current_ctx: dict) -> dict:
    entry_volume = _to_float(entry_snapshot.get("volume_velocity"))
    current_volume = _to_float(current_ctx.get("volume_velocity_now", current_ctx.get("volume_velocity")))

    entry_bundle = _to_float(entry_snapshot.get("bundle_cluster_score"))
    current_bundle = _to_float(current_ctx.get("bundle_cluster_score_now", current_ctx.get("bundle_cluster_score")))

    entry_x = _to_float(entry_snapshot.get("x_validation_score"))
    current_x = _to_float(current_ctx.get("x_validation_score_now", current_ctx.get("x_validation_score")))

    entry_liquidity = _to_float(entry_snapshot.get("liquidity_usd"), _to_float(current_ctx.get("liquidity_usd_entry")))
    current_liquidity = _to_float(current_ctx.get("liquidity_usd_now", current_ctx.get("liquidity_usd")))

    liquidity_drop_pct = 0.0
    if entry_liquidity > 0:
        liquidity_drop_pct = max(0.0, ((entry_liquidity - current_liquidity) / entry_liquidity) * 100.0)

    volume_ratio = 0.0
    if entry_volume > 0:
        volume_ratio = current_volume / entry_volume

    return {
        "liquidity_drop_pct": liquidity_drop_pct,
        "bundle_cluster_delta": current_bundle - entry_bundle,
        "x_validation_score_delta": current_x - entry_x,
        "volume_velocity_ratio_vs_entry": volume_ratio,
    }


def run_position_monitor(positions: list[dict], current_states: list[dict], settings: Settings) -> dict:
    from trading.exit_logic import decide_exits

    events_path = settings.PROCESSED_DATA_DIR / "exit_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "exit_evaluation_started", "count": len(positions)})

    decisions = decide_exits(positions, current_states, settings)
    for decision in decisions:
        event = "exit_hold_confirmed"
        if decision["exit_decision"] == "PARTIAL_EXIT":
            event = "exit_partial_triggered"
        elif decision["exit_decision"] == "FULL_EXIT":
            event = "exit_full_triggered"
        if decision.get("exit_reason") in {
            "dev_sell_detected",
            "rug_flag_triggered",
            "missing_current_state_failclosed",
            "kill_switch_triggered",
        }:
            append_jsonl(
                events_path,
                {
                    "ts": utc_now_iso(),
                    "event": "exit_hard_rule_triggered",
                    "position_id": decision.get("position_id"),
                    "token_address": decision.get("token_address"),
                    "exit_reason": decision.get("exit_reason"),
                    "hold_sec": decision.get("hold_sec"),
                    "pnl_pct": decision.get("pnl_pct"),
                },
            )

        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": event,
                "position_id": decision.get("position_id"),
                "token_address": decision.get("token_address"),
                "exit_reason": decision.get("exit_reason"),
                "hold_sec": decision.get("hold_sec"),
                "pnl_pct": decision.get("pnl_pct"),
            },
        )

    payload = {"contract_version": settings.EXIT_CONTRACT_VERSION, "generated_at": utc_now_iso(), "positions": decisions}
    write_json(settings.PROCESSED_DATA_DIR / "exit_decisions.json", payload)
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "exit_completed", "count": len(decisions)})
    return payload
