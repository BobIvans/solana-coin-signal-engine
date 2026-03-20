from __future__ import annotations

from src.promotion.guards import compute_position_sizing, evaluate_entry_guards, should_block_entry


BASE_CONFIG = {
    "modes": {
        "constrained_paper": {
            "open_positions": True,
            "max_open_positions": 1,
            "max_trades_per_day": 10,
            "allow_regimes": ["SCALP"],
            "position_size_scale": 0.5,
        },
        "expanded_paper": {
            "open_positions": True,
            "max_open_positions": 2,
            "max_trades_per_day": 20,
            "allow_regimes": ["SCALP", "TREND"],
            "position_size_scale": 1.0,
        },
    },
    "safety": {"max_daily_loss_pct": 8.0, "max_consecutive_losses": 4, "kill_switch_file": "runs/none.flag"},
    "degraded_x": {"constrained_policy": "watchlist_only", "expanded_policy": "reduced_size"},
}


def test_missing_evidence_stays_conservative_without_crashing():
    state = {"active_mode": "expanded_paper", "open_positions": [], "counters": {}, "consecutive_losses": 0}
    signal = {
        "signal_id": "missing",
        "token_address": "SoMissing111",
        "entry_decision": "SCALP",
        "regime": "SCALP",
        "recommended_position_pct": 0.28,
        "runtime_signal_partial_flag": True,
        "x_status": "unknown",
    }

    sizing = compute_position_sizing(signal, state, BASE_CONFIG)

    assert sizing["base_position_pct"] == 0.28
    assert sizing["effective_position_pct"] < 0.2
    assert sizing["partial_evidence_flag"] is True
    assert sizing["sizing_confidence"] < 0.3
    assert "missing_evidence_size_reduced" in sizing["sizing_reason_codes"]


def test_hard_block_remains_authoritative_even_when_sizing_exists():
    state = {"active_mode": "constrained_paper", "open_positions": [{"position_id": "already_open"}], "counters": {}, "consecutive_losses": 0}
    signal = {
        "signal_id": "blocked",
        "token_address": "SoBlocked111",
        "entry_decision": "TREND",
        "regime": "TREND",
        "recommended_position_pct": 0.40,
        "regime_confidence": 0.84,
        "runtime_signal_confidence": 0.83,
        "continuation_confidence": 0.72,
        "x_status": "healthy",
        "x_validation_score": 80,
    }

    guards = evaluate_entry_guards(signal, state, BASE_CONFIG)
    sizing = compute_position_sizing(signal, state, BASE_CONFIG)

    assert should_block_entry(guards) is True
    assert "max_open_positions_reached" in guards["hard_block_reasons"]
    assert "regime_not_allowed" in guards["hard_block_reasons"]
    assert sizing["effective_position_pct"] > 0
