import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.holder_metrics import compute_holder_metrics


def test_holder_metrics_compute_shares_and_heuristics():
    supply = {"value": {"amount": "1000000", "decimals": 6, "uiAmount": 1_000_000.0}}
    largest = {"value": [{"uiAmount": 100_000.0}, {"uiAmount": 50_000.0}, {"uiAmount": 25_000.0}]}

    metrics = compute_holder_metrics("mint", supply, largest)

    assert metrics["top1_holder_share"] == 0.1
    assert metrics["top20_holder_share"] == 0.175
    assert metrics["first50_holder_conc_est"] >= metrics["top20_holder_share"]
    assert "first50_holder_conc_est is heuristic" in metrics["holder_metrics_warnings"]
