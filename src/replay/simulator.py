from __future__ import annotations

from typing import Any

from .deterministic import stable_sort_records


def _regime(features: dict[str, Any], score: float) -> str:
    if score >= 82 and features.get("volume_velocity", 0) >= 4:
        return "SCALP"
    if score >= 70 and features.get("holder_growth_5m", 0) >= 10:
        return "TREND"
    return "IGNORE"


def apply_position_limits(signals: list[dict[str, Any]], *, max_open_positions: int, max_trades_per_day: int) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    open_count = 0
    traded = 0
    for sig in signals:
        decision = "SKIP"
        reasons = ["regime_ignore"]
        if sig["regime_candidate"] != "IGNORE":
            if traded >= max_trades_per_day:
                reasons = ["max_trades_per_day_reached"]
            elif open_count >= max_open_positions:
                reasons = ["max_open_positions_reached"]
            else:
                decision = "ENTER"
                reasons = ["score_ok", "buy_pressure_ok"]
                open_count += 1
                traded += 1
                open_count -= 1
        sig = {**sig, "decision": decision, "decision_reason_codes": reasons}
        accepted.append(sig)
    return accepted


def simulate_trade_exit(signal: dict[str, Any], idx: int) -> dict[str, Any]:
    base = 0.0001 + idx * 0.000001
    pnl = round((signal["final_score"] - 70.0) / 2.0, 4)
    exit_price = round(base * (1 + pnl / 100.0), 12)
    hold_sec = int(20 + idx % 40)
    return {
        "entry_price": round(base, 12),
        "exit_price": exit_price,
        "pnl_pct": pnl,
        "hold_sec": hold_sec,
        "exit_reason": "velocity_decay_after_18s" if signal["regime_candidate"] == "SCALP" else "trend_pullback",
    }


def simulate_signals(signals: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ordered = stable_sort_records(signals, ("ts", "token_address", "pair_address"))
    limited = apply_position_limits(
        ordered,
        max_open_positions=int(config.get("simulation", {}).get("max_open_positions", 1)),
        max_trades_per_day=int(config.get("simulation", {}).get("max_trades_per_day", 20)),
    )
    trades: list[dict[str, Any]] = []
    for idx, signal in enumerate(limited):
        signal["regime_candidate"] = _regime(signal["features"], signal["final_score"])
        if signal["decision"] != "ENTER":
            continue
        exit_data = simulate_trade_exit(signal, idx)
        trades.append(
            {
                "run_id": signal["run_id"],
                "trade_id": f"trade_{idx:05d}",
                "token_address": signal["token_address"],
                "regime": signal["regime_candidate"],
                "entry_ts": signal["ts"],
                "exit_ts": signal["ts"],
                **exit_data,
                "x_status_entry": signal["x_status"],
            }
        )
    positions = {"open_positions": [], "closed_positions": [t["trade_id"] for t in trades]}
    return limited, trades, positions
