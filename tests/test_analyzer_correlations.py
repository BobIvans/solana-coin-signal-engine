import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer_correlations import compute_metric_correlations


class DummySettings:
    POST_RUN_MIN_TRADES_FOR_CORRELATION = 5
    POST_RUN_OUTLIER_CLIP_PCT = 0.0


def test_correlations_compute_ok():
    rows = []
    for i in range(1, 8):
        rows.append({"bundle_cluster_score": float(i), "net_pnl_pct": float(i)})
    out = compute_metric_correlations(rows, ["bundle_cluster_score"], "net_pnl_pct", DummySettings())
    assert out[0]["status"] == "ok"
    assert out[0]["direction"] == "positive"


def test_correlations_insufficient_sample():
    rows = [{"bundle_cluster_score": 1.0, "net_pnl_pct": 1.0}]
    out = compute_metric_correlations(rows, ["bundle_cluster_score"], "net_pnl_pct", DummySettings())
    assert out[0]["status"] == "insufficient_sample"
