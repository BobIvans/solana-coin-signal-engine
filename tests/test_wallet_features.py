from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from src.wallets.features import compute_wallet_features, compute_wallet_netflow_bias, count_early_wallet_entries


def test_wallet_hits_counted_correctly():
    registry = {
        "w1": {"tier": "tier_1", "score": 0.9},
        "w2": {"tier": "tier_2", "score": 0.8},
    }
    token = {"wallet_events": [{"wallet_address": "w1", "age_sec": 10, "side": "buy"}, {"wallet_address": "w2", "age_sec": 200, "side": "sell"}]}
    features = compute_wallet_features(token, registry, {"tiers": {"tier_1_weight": 1.0, "tier_2_weight": 0.6}, "features": {"early_entry_window_sec": 120}})
    assert features["smart_wallet_hits"] == 2
    assert features["smart_wallet_tier1_hits"] == 1


def test_early_entry_hits_counted_correctly():
    assert count_early_wallet_entries([{"age_sec": 10}, {"age_sec": 121}], 120) == 1


def test_netflow_bias_computed_correctly():
    assert compute_wallet_netflow_bias([{"side": "buy"}, {"side": "sell"}, {"side": "buy"}]) > 0
