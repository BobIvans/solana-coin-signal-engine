import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.analyzer_slices import compute_analyzer_slices



def test_analyzer_slices_mark_tiny_samples_as_insufficient():
    rows = [
        {
            "position_id": "tiny-1",
            "regime_decision": "TREND",
            "net_pnl_pct": -4.0,
            "hold_sec": 120,
            "regime_confidence": 0.85,
            "creator_in_cluster_flag": True,
            "creator_cluster_penalty": 0.8,
            "cluster_concentration_ratio": 0.82,
            "bundle_sell_heavy_penalty": 0.9,
            "retry_manipulation_penalty": 0.8,
            "x_status": "degraded",
        }
    ]

    payload = compute_analyzer_slices(rows, min_sample=3, run_id="tiny", source="fixture")

    creator_slice = payload["slice_groups"]["cluster_bundle"]["creator_linked_underperformance"]
    assert creator_slice["status"] == "insufficient_sample"
    assert "insufficient_sample" in creator_slice["warnings"]

    low_sample = payload["recommendation_inputs"]["low_sample_slices"]
    assert "creator_linked_underperformance" in low_sample
    assert not payload["recommendation_inputs"]["actionable_slices"]
