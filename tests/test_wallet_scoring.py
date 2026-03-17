from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from src.wallets.scoring import apply_wallet_adjustment_to_final_score, compute_wallet_score_adjustment


def test_bonuses_penalties_applied_correctly():
    adjustment = compute_wallet_score_adjustment(
        {"smart_wallet_tier1_hits": 1, "smart_wallet_tier2_hits": 1, "smart_wallet_early_entry_hits": 1, "smart_wallet_netflow_bias": -0.1},
        {"scoring": {"tier1_bonus_score": 3, "tier2_bonus_score": 1, "early_entry_bonus_score": 2, "negative_netflow_penalty": 3, "max_wallet_bonus_score": 6}},
    )
    assert adjustment["wallet_bonus_score"] == 6
    assert adjustment["wallet_penalty_score"] == 3


def test_score_cap_respected():
    adjustment = compute_wallet_score_adjustment({"smart_wallet_tier1_hits": 1, "smart_wallet_tier2_hits": 1, "smart_wallet_early_entry_hits": 1}, {"scoring": {"tier1_bonus_score": 4, "tier2_bonus_score": 4, "early_entry_bonus_score": 4, "max_wallet_bonus_score": 6}})
    assert adjustment["wallet_bonus_score"] == 6


def test_no_auto_entry_side_effect():
    adjusted = apply_wallet_adjustment_to_final_score(40, {"wallet_bonus_score": 6, "wallet_penalty_score": 0}, {})
    assert adjusted == 46
