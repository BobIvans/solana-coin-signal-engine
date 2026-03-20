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
