from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.linkage_scorer import score_creator_dev_funder_linkage


def test_missing_evidence_degrades_safely_without_crash():
    out = score_creator_dev_funder_linkage([], creator_wallet=None, dev_wallet=None, early_buyer_wallets=None)

    assert out["linkage_status"] == "missing"
    assert out["linkage_risk_score"] is None
    assert out["linkage_warning"]
    assert out["linkage_confidence"] == 0.0


def test_malformed_evidence_emits_warning_and_avoids_unhandled_exception():
    participants = [
        {"wallet": {"broken": True}, "funder": ["bad"]},
        {"wallet": "creator_wallet", "funder": "shared_funder", "creator_linked": True},
        "totally_invalid",
    ]

    out = score_creator_dev_funder_linkage(
        participants,  # type: ignore[arg-type]
        creator_wallet="creator_wallet",
        early_buyer_wallets=[{"wallet": "buyer_bad"}],  # type: ignore[list-item]
    )

    assert out["linkage_status"] in {"partial", "missing"}
    assert out["linkage_warning"]
    assert "linkage_malformed" in out["linkage_reason_codes"]
    assert out["creator_wallet"] == "creator_wallet"
