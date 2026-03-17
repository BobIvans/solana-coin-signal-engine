from src.promotion.guards import effective_position_scale, evaluate_entry_guards


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
        "counters": {"trades_today": 0, "pnl_pct_today": -9.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_daily_loss_pct_breached" in result["hard_block_reasons"]


def test_hard_block_by_max_positions():
    state = {
        "active_mode": "constrained_paper",
        "open_positions": [{"id": "1"}],
        "counters": {"trades_today": 0, "pnl_pct_today": 0.0},
        "consecutive_losses": 0,
    }
    result = evaluate_entry_guards({"regime": "SCALP"}, state, BASE_CONFIG)
    assert "max_open_positions_reached" in result["hard_block_reasons"]


def test_soft_degraded_x_reduced_size():
    state = {"active_mode": "constrained_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    scale = effective_position_scale({"x_status": "degraded"}, state, BASE_CONFIG)
    assert scale == 0.5
