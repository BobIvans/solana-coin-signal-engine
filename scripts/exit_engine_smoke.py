"""Smoke runner for PR-8 exit engine."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings
from trading.position_monitor import run_position_monitor
from utils.io import write_json

_REQUIRED = {
    "position_id",
    "token_address",
    "exit_decision",
    "exit_fraction",
    "exit_reason",
    "hold_sec",
    "pnl_pct",
    "exit_snapshot",
    "exit_status",
    "decided_at",
    "contract_version",
}


def _validate(decision: dict) -> None:
    missing = sorted(_REQUIRED - set(decision.keys()))
    if missing:
        raise ValueError(f"schema violation: missing {missing}")
    if decision.get("exit_decision") not in {"HOLD", "PARTIAL_EXIT", "FULL_EXIT"}:
        raise ValueError("schema violation: invalid exit_decision")
    if decision.get("exit_decision") == "FULL_EXIT" and not decision.get("exit_reason"):
        raise ValueError("impossible state: FULL_EXIT requires reason")


def _base_position(regime: str = "SCALP") -> dict:
    return {
        "position_id": "pos_0001",
        "token_address": "So11111111111111111111111111111111111111112",
        "symbol": "EXAMPLE",
        "entry_decision": regime,
        "entry_time": "2026-03-15T12:30:41Z",
        "entry_price_usd": 1.0,
        "position_size_pct": 0.3,
        "partials_taken": [],
        "is_open": True,
        "entry_snapshot": {
            "final_score": 84.2,
            "buy_pressure": 0.81,
            "volume_velocity": 4.8,
            "liquidity_usd": 30000,
            "bundle_cluster_score": 0.66,
            "x_validation_score": 71.4,
            "x_status": "ok",
            "dev_sell_pressure_5m": 0.0,
            "rug_flag": False,
            "rug_score": 0.18,
        },
    }


def _base_state() -> dict:
    return {
        "token_address": "So11111111111111111111111111111111111111112",
        "now_ts": "2026-03-15T12:31:04Z",
        "price_usd_now": 1.124,
        "buy_pressure_now": 0.78,
        "volume_velocity_now": 4.6,
        "liquidity_usd_now": 29000,
        "x_validation_score_now": 70.0,
        "x_status_now": "ok",
        "bundle_cluster_score_now": 0.64,
        "dev_sell_pressure_now": 0.0,
        "rug_flag_now": False,
    }


def main() -> int:
    settings = load_settings()
    cases: list[tuple[str, dict, dict, str, str, str | None, list[str]]] = []

    pos = _base_position("SCALP")
    state = _base_state()
    state["price_usd_now"] = 0.88
<<<<<<< HEAD
    cases.append(("scalp_stop", pos, state, "FULL_EXIT", "scalp_stop_loss", "ok", []))
=======
    cases.append(("scalp_stop", pos, state, "FULL_EXIT", "scalp_stop_loss", settings))
>>>>>>> origin/main

    pos = _base_position("SCALP")
    state = _base_state()
    state["volume_velocity_now"] = 2.5
<<<<<<< HEAD
    cases.append(("scalp_recheck_decay", pos, state, "FULL_EXIT", "scalp_momentum_decay_after_recheck", "ok", []))
=======
    cases.append(("scalp_recheck_decay", pos, state, "FULL_EXIT", "scalp_momentum_decay_after_recheck", settings))
>>>>>>> origin/main

    pos = _base_position("TREND")
    state = _base_state()
    state["price_usd_now"] = 1.40
<<<<<<< HEAD
    cases.append(("trend_partial_1", pos, state, "PARTIAL_EXIT", "trend_partial_take_profit_1", "ok", []))
=======
    cases.append(("trend_partial_1", pos, state, "PARTIAL_EXIT", "trend_partial_take_profit_1", settings))
>>>>>>> origin/main

    pos = _base_position("TREND")
    state = _base_state()
    state["rug_flag_now"] = True
<<<<<<< HEAD
    cases.append(("trend_rug_hard", pos, state, "FULL_EXIT", "rug_flag_triggered", "ok", []))
=======
    cases.append(("trend_rug_hard", pos, state, "FULL_EXIT", "rug_flag_triggered", settings))
>>>>>>> origin/main

    pos = _base_position("SCALP")
    state = _base_state()
    state["now_ts"] = "2026-03-15T12:30:50Z"
    state["price_usd_now"] = 1.03
<<<<<<< HEAD
    cases.append(("healthy_hold", pos, state, "HOLD", "hold_conditions_intact", "ok", []))

    pos = _base_position("SCALP")
    state = _base_state()
    state.pop("x_validation_score_now")
    state.pop("bundle_cluster_score_now")
    state.pop("dev_sell_pressure_now")
    state["now_ts"] = "2026-03-15T12:30:50Z"
    state["price_usd_now"] = 1.03
    cases.append(
        (
            "degraded_poll_sticky_fallback",
            pos,
            state,
            "HOLD",
            "hold_conditions_intact",
            "partial",
            [
                "degraded_current_state_fields",
                "fallback_x_validation_score_now",
                "fallback_bundle_cluster_score_now",
                "fallback_dev_sell_pressure_now",
            ],
        )
    )
=======
    cases.append(("healthy_hold", pos, state, "HOLD", "hold_conditions_intact", settings))
>>>>>>> origin/main

    with tempfile.TemporaryDirectory() as tmpdir:
        kill_switch_path = Path(tmpdir) / "kill_switch.flag"
        kill_switch_path.write_text("armed\n", encoding="utf-8")
        kill_switch_settings = SimpleNamespace(**vars(settings), KILL_SWITCH_FILE=str(kill_switch_path))
        pos = _base_position("TREND")
        state = _base_state()
        cases.append(("kill_switch_forced_exit", pos, state, "FULL_EXIT", "kill_switch_triggered", kill_switch_settings))

<<<<<<< HEAD
    for name, position, current, expected_decision, expected_reason, expected_status, expected_warnings in cases:
        result = run_position_monitor([position], [current], settings)["positions"][0]
        _validate(result)
        if result["exit_decision"] != expected_decision:
            raise ValueError(f"{name}: expected {expected_decision}, got {result['exit_decision']}")
        if result["exit_reason"] != expected_reason:
            raise ValueError(f"{name}: expected reason {expected_reason}, got {result['exit_reason']}")
        if expected_status is not None and result["exit_status"] != expected_status:
            raise ValueError(f"{name}: expected status {expected_status}, got {result['exit_status']}")
        for warning in expected_warnings:
            if warning not in result.get("exit_warnings", []):
                raise ValueError(f"{name}: expected warning {warning}, got {result.get('exit_warnings', [])}")
=======
        selected_pos = cases[0][1]
        selected_state = cases[0][2]
        selected_settings = cases[0][5]
        payload = run_position_monitor([selected_pos], [selected_state], selected_settings)
        write_json(settings.PROCESSED_DATA_DIR / "exit_decisions.smoke.json", payload)
>>>>>>> origin/main

        for name, position, current, expected_decision, expected_reason, case_settings in cases:
            result = run_position_monitor([position], [current], case_settings)["positions"][0]
            _validate(result)
            if result["exit_decision"] != expected_decision:
                raise ValueError(f"{name}: expected {expected_decision}, got {result['exit_decision']}")
            if result["exit_reason"] != expected_reason:
                raise ValueError(f"{name}: expected reason {expected_reason}, got {result['exit_reason']}")

        print(json.dumps(payload["positions"][0], sort_keys=True, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
