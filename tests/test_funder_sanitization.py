from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.linkage_scorer import score_creator_dev_funder_linkage
from analytics.wallet_family_metadata import derive_wallet_family_metadata
from analytics.wallet_graph_builder import build_wallet_graph


def test_graph_sanitizes_ignorelisted_cex_funder():
    graph = build_wallet_graph([
        {"wallet": "wallet_a", "funder": "binance_hot_wallet_1"},
        {"wallet": "wallet_b", "funder": "binance_hot_wallet_1"},
    ])
    assert not any("shared_funder" in edge["evidence_types"] for edge in graph["edges"])


def test_linkage_sanitizes_ignorelisted_cex_funder():
    out = score_creator_dev_funder_linkage(
        [
            {"wallet": "creator_wallet", "funder": "binance_hot_wallet_1", "creator_linked": True},
            {"wallet": "buyer_a", "funder": "binance_hot_wallet_1"},
        ],
        creator_wallet="creator_wallet",
        early_buyer_wallets=["buyer_a"],
    )
    assert out["funder_overlap_count"] == 0
    assert out["ignored_shared_funder_count"] >= 1


def test_wallet_family_sanitizes_ignorelisted_cex_funder():
    derived = derive_wallet_family_metadata(
        [
            {"wallet": "wallet_a", "funder": "binance_hot_wallet_1"},
            {"wallet": "wallet_b", "funder": "binance_hot_wallet_1"},
        ],
        generated_at="2024-01-02T00:00:00Z",
    )
    by_wallet = {record["wallet"]: record for record in derived["wallet_records"]}
    assert by_wallet["wallet_a"]["wallet_family_shared_funder_flag"] is False
    assert by_wallet["wallet_a"]["wallet_family_funder_sanitization_applied"] is True


def test_unknown_funder_is_not_sanitized():
    graph = build_wallet_graph([
        {"wallet": "wallet_a", "funder": "rare_funder_alpha"},
        {"wallet": "wallet_b", "funder": "rare_funder_alpha"},
    ])
    assert any("shared_funder" in edge["evidence_types"] for edge in graph["edges"])
