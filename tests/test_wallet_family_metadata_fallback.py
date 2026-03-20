from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from analytics.wallet_family_metadata import derive_wallet_family_metadata


def test_missing_evidence_degrades_to_missing_without_fake_ids():
    derived = derive_wallet_family_metadata(
        [
            {"wallet": "wallet_missing_a"},
            {"wallet": "wallet_missing_b"},
        ],
        generated_at="2024-01-02T00:00:00Z",
    )

    for record in derived["wallet_records"]:
        assert record["wallet_family_id"] is None
        assert record["independent_family_id"] is None
        assert record["wallet_family_status"] == "missing"
        assert record["wallet_family_confidence"] == 0.0

    assert derived["summary"]["family_count"] == 0
    assert derived["summary"]["missing_assignments"] == 2


def test_malformed_inputs_emit_warnings_and_do_not_raise():
    derived = derive_wallet_family_metadata(
        [
            {"wallet": {"broken": True}, "funder": ["bad"]},
            {"wallet": "wallet_ok", "source_records": ["bad_record"], "linkage_confidence": "not-a-number"},
            "totally_invalid",
        ],  # type: ignore[list-item]
        generated_at="2024-01-02T00:00:00Z",
    )

    failed = [record for record in derived["wallet_records"] if record.get("wallet_family_status") == "failed"]
    assert failed
    assert derived["warnings"]
    assert derived["summary"]["failed_assignments"] >= 1
    ok_wallet = next(record for record in derived["wallet_records"] if record.get("wallet") == "wallet_ok")
    assert ok_wallet["wallet_family_id"] is None
    assert ok_wallet["wallet_family_status"] in {"missing", "failed"}
