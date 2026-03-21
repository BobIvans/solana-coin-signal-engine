from __future__ import annotations

from src.replay import historical_replay_harness as replay_harness
from src.replay.replay_state_machine import ReplayStateMachine


def _base_context() -> dict[str, object]:
    return {
        "entry_price": 1.0,
        "entry_price_usd": 1.0,
        "net_unique_buyers_60s": 11,
        "liquidity_refill_ratio_120s": 0.91,
        "cluster_sell_concentration_120s": 0.83,
        "seller_reentry_ratio": 0.41,
        "liquidity_shock_recovery_sec": 145,
        "x_author_velocity_5m": 0.12,
    }


def test_replay_masks_60s_metrics_before_60_seconds():
    masked = replay_harness._mask_future_window_metrics(_base_context(), 15)

    assert masked["net_unique_buyers_60s"] is None
    assert masked["liquidity_refill_ratio_120s"] is None
    assert masked["x_author_velocity_5m"] is None


def test_replay_masks_120s_metrics_before_120_seconds():
    masked = replay_harness._mask_future_window_metrics(_base_context(), 90)

    assert masked["net_unique_buyers_60s"] == 11
    assert masked["liquidity_refill_ratio_120s"] is None
    assert masked["cluster_sell_concentration_120s"] is None
    assert masked["seller_reentry_ratio"] is None
    assert masked["liquidity_shock_recovery_sec"] is None

    visible = replay_harness._mask_future_window_metrics(_base_context(), 150)
    assert visible["liquidity_refill_ratio_120s"] == 0.91
    assert visible["cluster_sell_concentration_120s"] == 0.83


def test_replay_masks_5m_x_metric_before_300_seconds():
    masked = replay_harness._mask_future_window_metrics(_base_context(), 150)
    visible = replay_harness._mask_future_window_metrics(_base_context(), 320)

    assert masked["x_author_velocity_5m"] is None
    assert visible["x_author_velocity_5m"] == 0.12


def test_replay_exit_evaluator_uses_masked_snapshot_not_full_base_context(monkeypatch):
    captured: dict[str, object] = {}

    def fake_hard_exit(position_ctx, current_ctx, settings):
        captured["entry_snapshot"] = dict(position_ctx.get("entry_snapshot") or {})
        captured["current_ctx"] = dict(current_ctx)
        return {"exit_decision": "HOLD", "exit_fraction": 0.0, "exit_reason": "hold", "exit_flags": [], "exit_warnings": []}

    def fake_scalp_exit(position_ctx, current_ctx, settings):
        captured["scalp_entry_snapshot"] = dict(position_ctx.get("entry_snapshot") or {})
        captured["scalp_current_ctx"] = dict(current_ctx)
        return {"exit_decision": "FULL_EXIT", "exit_fraction": 1.0, "exit_reason": "done", "exit_flags": [], "exit_warnings": []}

    monkeypatch.setattr(replay_harness, "evaluate_hard_exit", fake_hard_exit)
    monkeypatch.setattr(replay_harness, "evaluate_scalp_exit", fake_scalp_exit)

    state = ReplayStateMachine(token_address="tok_pti")
    state.candidate_seen()
    state.open_position(entry_time="2026-03-19T00:00:00Z", entry_price=1.0)

    result = replay_harness._resolve_exit(
        {
            **_base_context(),
            "cluster_sell_concentration_120s": 0.97,
            "liquidity_refill_ratio_120s": 0.2,
        },
        {"entry_price": 1.0, "entry_time": "2026-03-19T00:00:00Z"},
        {
            "price_paths": [
                {
                    "price_path": [
                        {"offset_sec": 15, "price": 1.01, "cluster_sell_concentration_120s": 0.99, "liquidity_refill_ratio_120s": 0.1},
                    ]
                }
            ]
        },
        "SCALP",
        state,
    )

    assert result["exit_decision"] == "FULL_EXIT"
    assert captured["entry_snapshot"]["cluster_sell_concentration_120s"] is None
    assert captured["entry_snapshot"]["liquidity_refill_ratio_120s"] is None
    assert captured["current_ctx"]["cluster_sell_concentration_120s"] is None
    assert captured["current_ctx"]["liquidity_refill_ratio_120s"] is None
