import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.x_validation_score import score_x_validation
from config.settings import load_settings


def _base_metrics():
    return {
        "x_status": "ok",
        "x_unique_authors_visible": 10,
        "x_posts_visible": 12,
        "x_weighted_engagement": 500,
        "x_official_account_match": 0,
        "x_contract_mention_presence": 0,
        "x_queries_succeeded": 3,
        "x_queries_attempted": 4,
        "x_duplicate_text_ratio": 0.2,
        "x_promoter_concentration": 0.3,
    }


def test_score_clamped_to_0_100():
    settings = load_settings()
    result = score_x_validation({**_base_metrics(), "x_weighted_engagement": 10_000_000}, settings)
    assert 0 <= result["x_validation_score"] <= 100


def test_degraded_score_path_stable(monkeypatch):
    monkeypatch.setenv("OPENCLAW_X_DEGRADED_SCORE", "45")
    settings = load_settings()
    result = score_x_validation({"x_status": "degraded"}, settings)
    assert result["x_validation_score"] == 45
    assert result["x_validation_delta"] == 0


def test_official_match_boosts_score():
    settings = load_settings()
    no_boost = score_x_validation(_base_metrics(), settings)
    with_boost = score_x_validation({**_base_metrics(), "x_official_account_match": 1}, settings)
    assert with_boost["x_validation_score"] > no_boost["x_validation_score"]


def test_promoter_concentration_penalizes_score():
    settings = load_settings()
    low = score_x_validation({**_base_metrics(), "x_promoter_concentration": 0.1}, settings)
    high = score_x_validation({**_base_metrics(), "x_promoter_concentration": 0.9}, settings)
    assert high["x_validation_score"] < low["x_validation_score"]
