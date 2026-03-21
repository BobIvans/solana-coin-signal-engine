from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.linkage_scorer import score_creator_dev_funder_linkage


def test_explicit_creator_to_early_buyer_linkage_scores_high_with_multiple_evidence_types():
    participants = [
        {"wallet": "creator_wallet", "funder": "shared_funder", "cluster_id": "cluster_1", "launch_group": "launch_alpha", "creator_linked": True},
        {"wallet": "buyer_a", "funder": "shared_funder", "cluster_id": "cluster_1", "launch_group": "launch_alpha", "creator_linked": True},
        {"wallet": "buyer_b", "funder": "shared_funder", "cluster_id": "cluster_2", "launch_group": "launch_alpha"},
    ]

    out = score_creator_dev_funder_linkage(
        participants,
        creator_wallet="creator_wallet",
        early_buyer_wallets=["buyer_a", "buyer_b"],
        cluster_ids_by_wallet={"creator_wallet": "cluster_1", "buyer_a": "cluster_1", "buyer_b": "cluster_2"},
        token_address="token_1",
    )

    assert out["creator_buyer_link_score"] >= 0.9
    assert out["shared_funder_link_score"] > 0
    assert out["linkage_risk_score"] >= 0.45
    assert out["linkage_confidence"] >= 0.55
    assert "creator_buyer_direct_link" in out["linkage_reason_codes"]
    assert "creator_buyer_same_funder" in out["linkage_reason_codes"]


def test_dev_wallet_linked_to_early_participants_scores_non_zero_conservatively():
    participants = [
        {"wallet": "dev_wallet", "funder": "dev_funder", "launch_group": "launch_beta", "dev_linked": True},
        {"wallet": "buyer_a", "funder": "dev_funder", "launch_group": "launch_beta", "dev_linked": True},
        {"wallet": "buyer_b", "funder": "other_funder", "launch_group": "launch_beta"},
    ]

    out = score_creator_dev_funder_linkage(
        participants,
        dev_wallet="dev_wallet",
        early_buyer_wallets=["buyer_a", "buyer_b"],
        token_address="token_2",
    )

    assert out["dev_buyer_link_score"] > 0.5
    assert out["linkage_risk_score"] > 0
    assert out["linkage_reason_codes"]
    assert out["linkage_metric_origin"] in {"heuristic_evidence", "mixed_evidence"}


def test_creator_dev_same_funder_without_buyer_overlap_does_not_overstate_risk():
    participants = [
        {"wallet": "creator_wallet", "funder": "shared_funder", "launch_group": "launch_gamma", "creator_linked": True},
        {"wallet": "dev_wallet", "funder": "shared_funder", "launch_group": "launch_gamma", "dev_linked": True},
        {"wallet": "buyer_a", "funder": "buyer_funder", "cluster_id": "cluster_x"},
    ]

    out = score_creator_dev_funder_linkage(
        participants,
        creator_wallet="creator_wallet",
        dev_wallet="dev_wallet",
        early_buyer_wallets=["buyer_a"],
        token_address="token_3",
    )

    assert out["creator_dev_link_score"] > 0
    assert out["creator_buyer_link_score"] <= 0.1
    assert out["linkage_risk_score"] is not None and out["linkage_risk_score"] < 0.35
    assert "creator_dev_same_funder" in out["linkage_reason_codes"]


def test_weak_ambiguous_overlap_stays_low_confidence_without_hard_flag():
    participants = [
        {"wallet": "creator_wallet", "launch_group": "launch_weak", "creator_linked": True},
        {"wallet": "buyer_a", "launch_group": "launch_weak"},
    ]

    out = score_creator_dev_funder_linkage(
        participants,
        creator_wallet="creator_wallet",
        early_buyer_wallets=["buyer_a"],
        token_address="token_4",
    )

    assert out["linkage_confidence"] < 0.55
    assert (out["linkage_risk_score"] or 0) <= 0.2
    assert out["creator_in_cluster_flag"] is None
    assert "shared_launch_group" in out["linkage_reason_codes"]


def test_common_exchange_funder_is_excluded_from_overlap_counts():
    participants = [
        {"wallet": "creator_wallet", "funder": "binance_hot_wallet_1", "creator_linked": True},
        {"wallet": "buyer_a", "funder": "binance_hot_wallet_1"},
    ]
    out = score_creator_dev_funder_linkage(
        participants,
        creator_wallet="creator_wallet",
        early_buyer_wallets=["buyer_a"],
        token_address="token_cex",
    )
    assert out["funder_overlap_count"] == 0
    assert out["creator_buyer_same_funder_flag"] is False
    assert out["ignored_shared_funder_count"] >= 1


def test_unknown_shared_funder_still_counts_for_linkage_risk():
    participants = [
        {"wallet": "creator_wallet", "funder": "rare_funder_alpha", "creator_linked": True},
        {"wallet": "buyer_a", "funder": "rare_funder_alpha"},
    ]
    out = score_creator_dev_funder_linkage(
        participants,
        creator_wallet="creator_wallet",
        early_buyer_wallets=["buyer_a"],
        token_address="token_unknown",
    )
    assert out["funder_overlap_count"] >= 1
    assert out["creator_buyer_same_funder_flag"] is True
