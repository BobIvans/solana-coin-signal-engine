import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from types import SimpleNamespace

from trading.position_monitor import compute_hold_sec, compute_pnl_pct, compute_position_deltas, run_position_monitor


def test_compute_hold_sec_utc_iso():
    assert compute_hold_sec("2026-03-15T12:30:41Z", "2026-03-15T12:31:04Z") == 23


def test_compute_pnl_pct():
    assert round(compute_pnl_pct(1.0, 1.124), 2) == 12.40


def test_compute_position_deltas():
    deltas = compute_position_deltas(
        {"volume_velocity": 4.8, "bundle_cluster_score": 0.66, "x_validation_score": 71.4, "liquidity_usd": 30000},
        {"volume_velocity_now": 3.1, "bundle_cluster_score_now": 0.41, "x_validation_score_now": 49.0, "liquidity_usd_now": 23700},
    )
    assert round(deltas["liquidity_drop_pct"], 1) == 21.0
    assert round(deltas["bundle_cluster_delta"], 2) == -0.25
    assert round(deltas["volume_velocity_ratio_vs_entry"], 4) == 0.6458


def test_run_position_monitor_emits_hard_rule_event_for_kill_switch(tmp_path):
    settings = SimpleNamespace(
        PROCESSED_DATA_DIR=tmp_path / "processed",
        EXIT_CONTRACT_VERSION="exit_engine_v1",
        EXIT_ENGINE_FAILCLOSED=True,
        EXIT_DEV_SELL_HARD=True,
        EXIT_RUG_FLAG_HARD=True,
        EXIT_SCALP_STOP_LOSS_PCT=-10,
        EXIT_SCALP_LIQUIDITY_DROP_PCT=20,
        EXIT_SCALP_MAX_HOLD_SEC=120,
        EXIT_SCALP_RECHECK_SEC=18,
        EXIT_SCALP_VOLUME_VELOCITY_DECAY=0.70,
        EXIT_SCALP_X_SCORE_DECAY=0.70,
        EXIT_SCALP_BUY_PRESSURE_FLOOR=0.60,
        EXIT_TREND_HARD_STOP_PCT=-18,
        EXIT_TREND_BUY_PRESSURE_FLOOR=0.50,
        EXIT_TREND_LIQUIDITY_DROP_PCT=25,
        EXIT_TREND_PARTIAL1_PCT=35,
        EXIT_TREND_PARTIAL2_PCT=100,
        EXIT_CLUSTER_DUMP_HARD=0.82,
        EXIT_CLUSTER_CONCENTRATION_SELL_THRESHOLD=0.65,
        EXIT_CLUSTER_SELL_CONCENTRATION_WARN=0.72,
        EXIT_CLUSTER_SELL_CONCENTRATION_HARD=0.78,
        EXIT_LIQUIDITY_REFILL_FAIL_MIN=0.85,
        EXIT_SELLER_REENTRY_WEAK_MAX=0.20,
        EXIT_SHOCK_RECOVERY_TOO_SLOW_SEC=180,
        EXIT_BUNDLE_FAILURE_SPIKE_THRESHOLD=2.0,
        EXIT_RETRY_MANIPULATION_HARD=5.0,
        EXIT_CREATOR_CLUSTER_RISK_HARD=0.75,
        KILL_SWITCH_FILE=str(tmp_path / "kill_switch.flag"),
    )
    Path(settings.KILL_SWITCH_FILE).write_text("armed\n", encoding="utf-8")

    positions = [
        {
            "position_id": "p1",
            "token_address": "So111",
            "symbol": "EX",
            "entry_decision": "SCALP",
            "entry_time": "2026-03-15T12:30:41Z",
            "entry_price_usd": 1.0,
            "entry_snapshot": {
                "volume_velocity": 4.8,
                "x_validation_score": 71.4,
                "bundle_cluster_score": 0.66,
                "liquidity_usd": 30000,
            },
            "is_open": True,
        }
    ]
    current_states = [
        {
            "token_address": "So111",
            "now_ts": "2026-03-15T12:31:04Z",
            "price_usd_now": 1.10,
            "buy_pressure_now": 0.80,
            "volume_velocity_now": 4.6,
            "liquidity_usd_now": 29500,
            "x_validation_score_now": 70.0,
            "x_status_now": "ok",
            "bundle_cluster_score_now": 0.67,
            "dev_sell_pressure_now": 0.0,
            "rug_flag_now": False,
        }
    ]

    payload = run_position_monitor(positions, current_states, settings)
    assert payload["positions"][0]["exit_reason"] == "kill_switch_triggered"

    events = [
        json.loads(line)
        for line in (settings.PROCESSED_DATA_DIR / "exit_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    hard_events = [event for event in events if event.get("event") == "exit_hard_rule_triggered"]
    assert hard_events
    assert hard_events[0]["exit_reason"] == "kill_switch_triggered"
