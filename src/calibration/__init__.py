"""Replay calibration package."""

from .evaluator import compute_metrics, detect_regime_collapse, evaluate_candidate
from .grid import build_candidate_grid, limit_candidates
from .leaderboard import compare_to_baseline, rank_candidates
from .recommender import build_recommended_config, recommend_candidate
from .splits import build_day_splits

__all__ = [
    "build_candidate_grid",
    "limit_candidates",
    "build_day_splits",
    "compute_metrics",
    "detect_regime_collapse",
    "evaluate_candidate",
    "compare_to_baseline",
    "rank_candidates",
    "recommend_candidate",
    "build_recommended_config",
]
