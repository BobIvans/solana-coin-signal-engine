"""Recommendation logic with anti-overfitting constraints."""

from __future__ import annotations


def _passes_constraints(candidate: dict, constraints: dict) -> bool:
    min_total = int(constraints.get("min_trades_total", 0))
    min_regime = int(constraints.get("min_trades_per_regime", 0))

    v_metrics = candidate.get("validation", {})
    regimes = candidate.get("regimes", {})
    if int(v_metrics.get("trades", 0)) < min_total:
        return False
    if int(regimes.get("scalp_trades", 0)) < min_regime:
        return False
    if int(regimes.get("trend_trades", 0)) < min_regime:
        return False
    if candidate.get("regime_collapsed"):
        return False
    if float(v_metrics.get("expectancy", 0.0)) < -0.5:
        return False
    return True


def recommend_candidate(leaderboard: list[dict], constraints: dict) -> dict | None:
    require_baseline_outperformance = bool(constraints.get("require_baseline_outperformance", True))
    for candidate in leaderboard:
        if candidate.get("candidate_id") == "baseline":
            continue
        if not candidate.get("passes_constraints", False):
            continue
        if require_baseline_outperformance and not candidate.get("beats_baseline", False):
            continue
        return candidate
    return None


def build_recommended_config(candidate: dict) -> dict:
    return {
        "overrides": candidate.get("config_diff_from_baseline", {}),
        "selection_basis": {
            "primary_metric": candidate.get("primary_metric", "validation_expectancy"),
            "baseline_replay_run_id": candidate.get("replay_run_id"),
            "candidate_id": candidate.get("candidate_id"),
        },
    }


def annotate_constraints(leaderboard: list[dict], constraints: dict) -> list[dict]:
    for candidate in leaderboard:
        candidate["passes_constraints"] = _passes_constraints(candidate, constraints)
    return leaderboard
