from src.promotion.guards import compute_position_sizing, effective_position_scale, evaluate_entry_guards


BASE_CONFIG = {
    "modes": {
        "constrained_paper": {
            "open_positions": True,
            "max_open_positions": 1,
            "max_trades_per_day": 10,
            "allow_regimes": ["SCALP"],
            "position_size_scale": 1.0,
        }
    },
    "safety": {"max_daily_loss_pct": 8.0, "max_consecutive_losses": 4, "kill_switch_file": "runs/none.flag"},
    "degraded_x": {"constrained_policy": "reduced_size"},
}


def test_hard_block_by_daily_loss_cap():
    state = {
        "active_mode": "constrained_paper",
        "open_positions": [],
        "counters": {"trades_today": 0, "pnl_pct_today": -9.0, "realized_pnl_sol_today": -0.09, "starting_capital_sol": 1.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_daily_loss_pct_breached" in result["hard_block_reasons"]


def test_hard_block_by_max_positions():
    state = {
        "active_mode": "constrained_paper",
        "open_positions": [{"id": "1"}],
        "counters": {"trades_today": 0, "pnl_pct_today": 0.0, "realized_pnl_sol_today": 0.0, "starting_capital_sol": 1.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_open_positions_reached" in result["hard_block_reasons"]


def test_soft_degraded_x_reduced_size():
    state = {"active_mode": "constrained_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    scale = effective_position_scale({"x_status": "degraded"}, state, BASE_CONFIG)
    assert scale == 0.5


def test_position_sizing_adds_evidence_weighted_fields():
    state = {"active_mode": "constrained_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    signal = {
        "signal_id": "guard_size",
        "token_address": "SoGuard111",
        "entry_decision": "SCALP",
        "regime": "SCALP",
        "x_status": "healthy",
        "recommended_position_pct": 0.4,
        "regime_confidence": 0.8,
        "runtime_signal_confidence": 0.82,
        "continuation_confidence": 0.7,
        "continuation_status": "confirmed",
        "linkage_confidence": 0.8,
        "linkage_risk_score": 0.1,
        "x_validation_score": 78,
    }
    sizing = compute_position_sizing(signal, state, BASE_CONFIG)
    assert sizing["base_position_pct"] == 0.4
    assert sizing["effective_position_pct"] == 0.4
    assert sizing["sizing_multiplier"] == 1.0
    assert sizing["sizing_reason_codes"]


def test_daily_loss_guard_uses_realized_capital_drawdown_not_sum_of_trade_percents():
    state = {
        "active_mode": "constrained_paper",
        "open_positions": [],
        "counters": {"trades_today": 2, "pnl_pct_today": -20.0, "realized_pnl_sol_today": -0.04, "starting_capital_sol": 1.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_daily_loss_pct_breached" not in result["hard_block_reasons"]


def test_daily_loss_guard_blocks_on_realized_drawdown_from_capital():
    state = {
        "active_mode": "constrained_paper",
        "open_positions": [],
        "counters": {"trades_today": 2, "pnl_pct_today": -4.0, "realized_pnl_sol_today": -0.09, "starting_capital_sol": 1.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_daily_loss_pct_breached" in result["hard_block_reasons"]

from src.promotion.cooldowns import observe_x_signal, register_degraded_x_entry_opened


EXPANDED_CONFIG = {
    "modes": {
        "expanded_paper": {
            "open_positions": True,
            "max_open_positions": 3,
            "max_trades_per_day": 20,
            "allow_regimes": ["SCALP", "TREND"],
            "position_size_scale": 1.0,
        }
    },
    "safety": {"max_daily_loss_pct": 8.0, "max_consecutive_losses": 4, "kill_switch_file": "runs/none.flag"},
    "degraded_x": {
        "expanded_policy": "reduced_size",
        "max_entries_per_hour": 2,
        "max_consecutive_signals_for_entry": 2,
        "escalation_policy": "watchlist_only",
    },
}


def test_degraded_x_budget_exhaustion_blocks_new_entries():
    state = {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    register_degraded_x_entry_opened(state)
    register_degraded_x_entry_opened(state)
    observe_x_signal({"x_status": "degraded"}, state, EXPANDED_CONFIG)

    result = evaluate_entry_guards({"regime": "SCALP", "x_status": "degraded"}, state, EXPANDED_CONFIG)
    assert "degraded_x_budget_exhausted" in result["hard_block_reasons"]


def test_degraded_x_escalation_blocks_after_prolonged_streak():
    state = {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    for _ in range(3):
        observe_x_signal({"x_status": "degraded"}, state, EXPANDED_CONFIG)

    result = evaluate_entry_guards({"regime": "SCALP", "x_status": "degraded"}, state, EXPANDED_CONFIG)
    assert "degraded_x_escalated_to_watchlist_only" in result["hard_block_reasons"]
