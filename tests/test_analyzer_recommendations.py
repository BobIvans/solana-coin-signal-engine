import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer_recommendations import generate_recommendations


class DummySettings:
    POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION = 5
    POST_RUN_RECOMMENDATION_CONFIDENCE_MIN = 0.55


def test_recommendations_include_weight_adjustment_and_warning():
    summary = {
        "total_positions_closed": 3,
        "friction_summary": {"failed_fill_rate": 0.25},
    }
    correlations = [
        {
            "metric": "bundle_cluster_score",
            "status": "ok",
            "sample_size": 8,
            "pearson_corr": 0.4,
            "spearman_corr": 0.45,
        }
    ]
    slices = {"regime": {}, "x_status": {"degraded": {"count": 6}}}
    recs = generate_recommendations(summary, correlations, slices, DummySettings())
    assert any(r["type"] == "sample_size_warning" for r in recs)
    assert any(r["type"] == "weight_adjustment" for r in recs)
    assert any(r["type"] == "friction_model_adjustment" for r in recs)
