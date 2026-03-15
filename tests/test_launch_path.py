import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.launch_path import estimate_launch_path


def test_estimate_launch_path_detects_pumpfun_to_raydium():
    txs = [
        {"timestamp": 100, "description": "pumpfun launch", "type": "CREATE_POOL"},
        {"timestamp": 250, "description": "raydium swap", "type": "SWAP"},
    ]
    result = estimate_launch_path({}, txs)
    assert result["launch_path_label"] == "pumpfun_to_raydium_est"
    assert result["pumpfun_to_raydium_sec"] == 150
