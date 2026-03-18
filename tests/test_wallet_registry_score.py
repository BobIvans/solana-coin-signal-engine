from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from analytics.wallet_registry_score import compute_regime_fit, compute_registry_score, tag_quality_score


def test_tags_affect_score_deterministically():
    base = compute_registry_score(
        manual_priority=True,
        source_count=1,
        tags=[],
        notes="",
        format_confidence=1.0,
    )
    tagged = compute_registry_score(
        manual_priority=True,
        source_count=1,
        tags=["trend_candidate", "high_conviction", "manual_bulk"],
        notes="",
        format_confidence=1.0,
    )
    assert tagged > base
    assert tag_quality_score(["manual_bulk", "high_conviction", "trend_candidate"]) == tag_quality_score([
        "trend_candidate",
        "high_conviction",
        "manual_bulk",
    ])


def test_regime_fit_uses_tags_and_notes():
    scalp, trend = compute_regime_fit(["scalp_candidate", "replay_winner"], "trend follow notes")
    assert scalp > 0.7
    assert trend > 0.4
