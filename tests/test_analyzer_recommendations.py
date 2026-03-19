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


def test_recommendations_include_matrix_evidence_actions():
    summary = {
        "total_positions_closed": 8,
        "matrix_analysis_available": True,
        "friction_summary": {"failed_fill_rate": 0.0},
        "regime_confusion_summary": {
            "regime_confidence_buckets": {
                "regime_confidence:gte_0.7": {"count": 5, "avg_net_pnl_pct": 7.0},
                "regime_confidence:lt_0.7": {"count": 5, "avg_net_pnl_pct": 1.0},
            }
        },
        "trend_failure_summary": {"count": 5, "avg_net_pnl_pct": -6.0},
        "scalp_missed_trend_summary": {"count": 5, "avg_mfe_capture_gap_pct": 14.0},
        "pattern_expectancy_slices": {
            "creator_in_cluster_flag:true": {"count": 5, "avg_net_pnl_pct": -4.0},
            "cluster_concentration_ratio:gte_0.6": {"count": 5, "avg_net_pnl_pct": -3.5},
            "retry_manipulation_penalty:gte_0.5": {"count": 5, "avg_net_pnl_pct": -2.5},
            "bundle_sell_heavy_penalty:gte_0.5": {"count": 5, "avg_net_pnl_pct": -2.0},
        },
    }
    recs = generate_recommendations(summary, [], {"regime": {}, "x_status": {}}, DummySettings())
    targets = {rec["target"] for rec in recs}
    assert "TREND promotion guard" in targets
    assert "SCALP->TREND upgrade path" in targets
    assert "creator-linked clusters" in targets
    assert "cluster concentration" in targets
