from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from analytics.wallet_family_metadata import assign_wallet_family_ids, derive_wallet_family_metadata
from scripts.build_wallet_registry import build_registry_artifacts

WALLET_A = "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty"
WALLET_B = "9xQeWvG816bUx9EPf8x7M7fD5kX4gG9f7N1n2s3t4u5v"
WALLET_C = "7M5xJ8gH2kL9pQ3rT6vW1yZ4bN8mD2sF5hJ7kL9mN2pQ"
WALLET_D = "6b8mQpR4xT2vY7nJ5kL1sD9fG3hW6cV8pN2rM4tY7uQ"
WALLET_E = "5QwErTyUiOpAsDfGhJkLzXcVbNm123456789ABCDEFG"
WALLET_F = "8ZyXwVuTsRqPoNmLkJiHgFeDcBa987654321ABCDE"
WALLET_G = "3AbCdEfGhIjKlMnOpQrStUvWxYz123456789ABCDE"
WALLET_H = "2BcDeFgHiJkLmNoPqRsTuVwXyZ987654321ABCDEF"
WALLET_I = "1CdEfGhIjKlMnOpQrStUvWxYzA987654321BCDEFG"


def test_assign_wallet_family_ids_is_member_stable():
    groups = [["wallet_b", "wallet_a"], ["wallet_d", "wallet_c"]]
    first = assign_wallet_family_ids(groups)
    second = assign_wallet_family_ids([["wallet_a", "wallet_b"], ["wallet_c", "wallet_d"]])

    assert first == second
    assert first["wallet_a"].startswith("wallet_family_")


def test_wallet_family_metadata_distinguishes_strong_loose_heuristic_and_missing_groups():
    records = [
        {
            "wallet": WALLET_A,
            "wallet_cluster_id": "cluster_strong",
            "funder": "funder_strong",
            "launch_group": ["launch_1", "launch_2"],
            "linkage_group": "linkage_strong",
            "linked_wallets": [WALLET_B],
            "creator_linked": True,
        },
        {
            "wallet": WALLET_B,
            "wallet_cluster_id": "cluster_strong",
            "funder": "funder_strong",
            "launch_group": ["launch_1", "launch_2"],
            "linkage_group": "linkage_strong",
            "linked_wallets": [WALLET_A],
            "creator_linked": True,
        },
        {"wallet": WALLET_C, "wallet_cluster_id": "cluster_loose"},
        {"wallet": WALLET_D, "wallet_cluster_id": "cluster_loose"},
        {"wallet": WALLET_E, "funder": "shared_hint_funder"},
        {"wallet": WALLET_F, "funder": "shared_hint_funder"},
        {"wallet": WALLET_G, "creator_linked": True, "linkage_group": "creator_slice"},
        {"wallet": WALLET_H, "creator_linked": True, "linkage_group": "creator_slice"},
        {"wallet": WALLET_I},
    ]

    derived = derive_wallet_family_metadata(records, generated_at="2024-01-02T00:00:00Z")
    by_wallet = {record["wallet"]: record for record in derived["wallet_records"]}

    assert by_wallet[WALLET_A]["wallet_family_id"] == by_wallet[WALLET_B]["wallet_family_id"]
    assert by_wallet[WALLET_A]["independent_family_id"] == by_wallet[WALLET_B]["independent_family_id"]
    assert by_wallet[WALLET_A]["wallet_family_confidence"] >= 0.9
    assert "shared_cluster_membership" in by_wallet[WALLET_A]["wallet_family_reason_codes"]

    assert by_wallet[WALLET_C]["wallet_family_id"] == by_wallet[WALLET_D]["wallet_family_id"]
    assert by_wallet[WALLET_C]["independent_family_id"] is None
    assert by_wallet[WALLET_C]["wallet_family_status"] == "partial"

    assert by_wallet[WALLET_E]["wallet_family_id"] == by_wallet[WALLET_F]["wallet_family_id"]
    assert by_wallet[WALLET_E]["wallet_family_confidence"] == 0.25
    assert by_wallet[WALLET_E]["wallet_family_shared_funder_flag"] is True
    assert by_wallet[WALLET_E]["independent_family_id"] is None

    assert by_wallet[WALLET_G]["wallet_family_id"] == by_wallet[WALLET_H]["wallet_family_id"]
    assert by_wallet[WALLET_G]["wallet_family_creator_link_flag"] is True
    assert by_wallet[WALLET_G]["independent_family_id"] is None

    assert by_wallet[WALLET_I]["wallet_family_id"] is None
    assert by_wallet[WALLET_I]["wallet_family_status"] == "missing"
    assert derived["summary"]["family_count"] == 4
    assert derived["summary"]["independent_family_count"] == 1


def test_wallet_family_metadata_is_additively_integrated_into_registry_outputs(tmp_path: Path):
    candidates = [
        {
            "wallet": WALLET_A,
            "status": "candidate",
            "source_names": ["seed_a"],
            "source_count": 1,
            "source_records": [{"cluster_id": "cluster_seed", "funder": "seed_funder", "launch_group": ["launch_1", "launch_2"]}],
            "imported_at": "2024-01-01T00:00:00Z",
            "manual_priority": True,
            "tags": ["high_conviction", "replay_winner"],
            "notes": "strong family seed",
            "wallet_cluster_id": "cluster_seed",
            "funder": "seed_funder",
            "launch_group": ["launch_1", "launch_2"],
        },
        {
            "wallet": WALLET_B,
            "status": "candidate",
            "source_names": ["seed_b"],
            "source_count": 1,
            "source_records": [{"cluster_id": "cluster_seed", "funder": "seed_funder", "launch_group": ["launch_1", "launch_2"]}],
            "imported_at": "2024-01-01T00:00:00Z",
            "manual_priority": True,
            "tags": ["trend_candidate", "tier2_hint"],
            "notes": "linked family seed",
            "wallet_cluster_id": "cluster_seed",
            "funder": "seed_funder",
            "launch_group": ["launch_1", "launch_2"],
        },
        {
            "wallet": WALLET_C,
            "status": "candidate",
            "source_names": ["seed_c"],
            "source_count": 1,
            "source_records": [],
            "imported_at": "2024-01-01T00:00:00Z",
            "manual_priority": True,
            "tags": [],
            "notes": "",
        },
    ]
    in_path = tmp_path / "normalized_wallet_candidates.json"
    payload = {
        "contract_version": "wallet_seed_import.v1",
        "generated_at": "2024-01-01T00:00:00Z",
        "input_summary": {"total_rows_seen": 3},
        "candidates": candidates,
    }
    in_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    registry, watch, hot, _ = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z", max_watchlist=10, max_hot=10, max_active=10)

    by_wallet = {record["wallet"]: record for record in registry["wallets"]}
    assert registry["wallet_family_summary"]["family_count"] == 1
    assert registry["wallet_family_assignments"]
    assert by_wallet[WALLET_A]["wallet_family_id"] == by_wallet[WALLET_B]["wallet_family_id"]
    assert by_wallet[WALLET_C]["wallet_family_id"] is None
    assert watch["wallets"][0]["wallet_family_id"] is not None
    assert hot["wallets"][0]["wallet_family_id"] is not None


def test_common_exchange_funder_does_not_raise_wallet_family_shared_funder_flag():
    records = [
        {"wallet": WALLET_A, "funder": "binance_hot_wallet_1"},
        {"wallet": WALLET_B, "funder": "binance_hot_wallet_1"},
    ]
    derived = derive_wallet_family_metadata(records, generated_at="2024-01-02T00:00:00Z")
    by_wallet = {record["wallet"]: record for record in derived["wallet_records"]}
    assert by_wallet[WALLET_A]["wallet_family_shared_funder_flag"] is False
    assert by_wallet[WALLET_A]["wallet_family_funder_sanitization_applied"] is True


def test_unknown_shared_funder_still_can_raise_wallet_family_reason():
    records = [
        {"wallet": WALLET_A, "funder": "rare_funder_alpha"},
        {"wallet": WALLET_B, "funder": "rare_funder_alpha"},
    ]
    derived = derive_wallet_family_metadata(records, generated_at="2024-01-02T00:00:00Z")
    by_wallet = {record["wallet"]: record for record in derived["wallet_records"]}
    assert by_wallet[WALLET_A]["wallet_family_shared_funder_flag"] is True
    assert "shared_funder" in by_wallet[WALLET_A]["wallet_family_reason_codes"]
