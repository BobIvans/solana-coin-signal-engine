from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from scripts.build_wallet_registry import build_registry_artifacts, write_registry_artifacts

WALLET_A = "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty"
WALLET_B = "9xQeWvG816bUx9EPf8x7M7fD5kX4gG9f7N1n2s3t4u5v"
WALLET_C = "7M5xJ8gH2kL9pQ3rT6vW1yZ4bN8mD2sF5hJ7kL9mN2pQ"
WALLET_D = "6b8mQpR4xT2vY7nJ5kL1sD9fG3hW6cV8pN2rM4tY7uQ"
WALLET_E = "5QwErTyUiOpAsDfGhJkLzXcVbNm123456789ABCDEFG"


def _write_input(path: Path, candidates: list[dict]) -> None:
    payload = {
        "contract_version": "wallet_seed_import.v1",
        "generated_at": "2024-01-01T00:00:00Z",
        "input_summary": {
            "total_rows_seen": len(candidates),
            "valid_wallets": sum(1 for item in candidates if len(item["wallet"]) >= 32),
            "invalid_rows": sum(1 for item in candidates if len(item["wallet"]) < 32),
            "duplicates_removed": 0,
        },
        "candidates": candidates,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate(wallet: str, *, manual_priority: bool = True, tags: list[str] | None = None, notes: str = "", source_count: int = 1) -> dict:
    return {
        "wallet": wallet,
        "status": "candidate",
        "source_names": [f"source_{idx}" for idx in range(source_count)],
        "source_count": source_count,
        "source_records": [],
        "imported_at": "2024-01-01T00:00:00Z",
        "manual_priority": manual_priority,
        "tags": tags or [],
        "notes": notes,
    }


def test_valid_candidates_become_tiered_deterministically(tmp_path: Path):
    in_path = tmp_path / "normalized_wallet_candidates.json"
    _write_input(
        in_path,
        [
            _candidate(WALLET_A, tags=["high_conviction", "replay_winner", "scalp_candidate"], notes="best"),
            _candidate(WALLET_B, tags=["trend_candidate", "tier2_hint"], notes="swing"),
            _candidate(WALLET_C, tags=[], notes=""),
        ],
    )

    registry, watch, hot, events = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z", max_watchlist=10, max_hot=10, max_active=2)
    by_wallet = {item["wallet"]: item for item in registry["wallets"]}

    assert by_wallet[WALLET_A]["tier"] == "tier_1"
    assert by_wallet[WALLET_B]["tier"] == "tier_2"
    assert by_wallet[WALLET_C]["tier"] == "tier_3"
    assert by_wallet[WALLET_C]["status"] == "watch"
    assert hot["wallets"][0]["wallet"] == WALLET_A
    assert any(event["wallet"] == WALLET_A for event in events)
    assert watch["watchlist_summary"]["selected_wallets"] == 3


def test_invalid_entries_become_rejected_and_logged(tmp_path: Path):
    in_path = tmp_path / "normalized_wallet_candidates.json"
    _write_input(in_path, [_candidate("bad_wallet", manual_priority=True)])

    registry, _, _, events = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z")
    record = registry["wallets"][0]
    assert record["status"] == "rejected"
    assert record["tier"] == "rejected"
    assert "rejected_invalid_wallet" in record["filter_reasons"]
    assert any(event["reason"] == "rejected_invalid_wallet" for event in events)


def test_sparse_manual_seeds_become_watch_not_rejected(tmp_path: Path):
    in_path = tmp_path / "normalized_wallet_candidates.json"
    _write_input(in_path, [_candidate(WALLET_A, tags=[], notes="", source_count=1)])

    registry, _, hot, _ = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z")
    record = registry["wallets"][0]
    assert record["tier"] == "tier_3"
    assert record["status"] == "watch"
    assert hot["wallets"] == []


def test_deterministic_ordering_and_bounds(tmp_path: Path):
    in_path = tmp_path / "normalized_wallet_candidates.json"
    _write_input(
        in_path,
        [
            _candidate(WALLET_D, tags=["trend_candidate"], notes="x", source_count=1),
            _candidate(WALLET_A, tags=["high_conviction", "replay_winner"], notes="x", source_count=3),
            _candidate(WALLET_C, tags=[], notes=""),
            _candidate(WALLET_B, tags=["trend_candidate", "tier2_hint"], notes="x", source_count=2),
            _candidate(WALLET_E, tags=["scalp_candidate"], notes="x", source_count=2),
        ],
    )

    registry, watch, hot, _ = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z", max_watchlist=3, max_hot=2, max_active=2)
    assert len(watch["wallets"]) == 3
    assert len(hot["wallets"]) == 2
    assert [item["wallet"] for item in hot["wallets"]] == [WALLET_A, WALLET_B]
    assert [item["status"] for item in watch["wallets"]][:2] == ["active", "active"]
    assert registry["registry_summary"]["active_count"] == 2


def test_same_input_yields_byte_stable_json_outputs(tmp_path: Path):
    in_path = tmp_path / "normalized_wallet_candidates.json"
    _write_input(in_path, [_candidate(WALLET_A, tags=["high_conviction", "replay_winner"], notes="x", source_count=2)])

    def run_once(out_dir: Path) -> tuple[str, str, str]:
        registry, watch, hot, events = build_registry_artifacts(in_path, generated_at="2024-01-02T00:00:00Z", max_watchlist=5, max_hot=5, max_active=5)
        reg_path = out_dir / "smart_wallets.json"
        watch_path = out_dir / "active_watchlist.json"
        hot_path = out_dir / "hot_wallets.json"
        event_path = out_dir / "filter_events.jsonl"
        write_registry_artifacts(
            registry_payload=registry,
            watch_payload=watch,
            hot_payload=hot,
            events=events,
            out_path=reg_path,
            watch_out_path=watch_path,
            hot_out_path=hot_path,
            event_log_path=event_path,
        )
        return (
            hashlib.sha256(reg_path.read_bytes()).hexdigest(),
            hashlib.sha256(watch_path.read_bytes()).hexdigest(),
            hashlib.sha256(hot_path.read_bytes()).hexdigest(),
        )

    first = run_once(tmp_path / "run1")
    second = run_once(tmp_path / "run2")
    assert first == second
