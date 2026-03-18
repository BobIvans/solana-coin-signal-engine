from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics.wallet_replay_validation import (
    ReplayInputError,
    ValidationThresholds,
    evaluate_wallet_registry_replay,
)


FIXED_TS = "2026-03-18T00:00:00Z"


def _wallet_record(wallet: str, *, tier: str, status: str = "watch", registry_score: float = 0.7) -> dict:
    return {
        "wallet": wallet,
        "status": status,
        "tier": tier,
        "registry_score": registry_score,
        "source_names": ["manual_seed"],
        "source_count": 1,
        "manual_priority": True,
        "tags": ["manual_bulk"],
        "notes": "",
        "quality_flags": {
            "invalid_format_rejected": False,
            "duplicate_source_merged": False,
            "manual_seed": True,
            "sparse_metadata": False,
            "requires_replay_validation": True,
        },
        "filter_reasons": ["kept_manual_seed"],
        "regime_fit_scalp": 0.2,
        "regime_fit_trend": 0.2,
        "watch_priority": registry_score,
        "hot_priority": registry_score,
        "added_at": FIXED_TS,
        "updated_at": FIXED_TS,
    }


def _write_registry(path: Path, wallets: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract_version": "smart_wallet_registry.v1",
        "generated_at": FIXED_TS,
        "input_summary": {"valid_wallets": len(wallets)},
        "registry_summary": {
            "total_candidates": len(wallets),
            "kept_wallets": len(wallets),
            "rejected_wallets": 0,
            "tier_1_count": sum(1 for item in wallets if item["tier"] == "tier_1"),
            "tier_2_count": sum(1 for item in wallets if item["tier"] == "tier_2"),
            "tier_3_count": sum(1 for item in wallets if item["tier"] == "tier_3"),
            "active_count": sum(1 for item in wallets if item["status"] == "active"),
            "watch_count": sum(1 for item in wallets if item["status"] == "watch"),
        },
        "wallets": wallets,
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _run_eval(tmp_path: Path, wallets: list[dict], replay_records: list[dict], *, max_hot: int = 100) -> dict:
    registry_path = _write_registry(tmp_path / "smart_wallets.json", wallets)
    tmp_path.mkdir(parents=True, exist_ok=True)
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "paper_trades.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in replay_records) + "\n",
        encoding="utf-8",
    )
    event_log = tmp_path / "promotion_events.jsonl"
    return evaluate_wallet_registry_replay(
        registry_path=registry_path,
        processed_dir=processed_dir,
        out_report=tmp_path / "replay_validation_report.json",
        out_registry=tmp_path / "smart_wallets.validated.json",
        out_hot=tmp_path / "hot_wallets.validated.json",
        event_log=event_log,
        generated_at=FIXED_TS,
        thresholds=ValidationThresholds(max_hot_validated=max_hot),
    )


def test_wallet_promotion_when_evidence_thresholds_met(tmp_path: Path):
    wallet = "wallet-promote"
    replay_records = [
        {"token_address": f"token-{idx}", "pnl_pct": 18.0, "hold_sec": 120, "wallets": [wallet]}
        for idx in range(10)
    ]
    result = _run_eval(tmp_path, [_wallet_record(wallet, tier="tier_2")], replay_records)
    validated = result["validated_registry"]["wallets"][0]
    assert validated["new_tier"] == "tier_1"
    assert validated["new_status"] == "active"
    assert validated["promotion_decision"] == "promote"
    assert validated["replay_evidence"]["replay_tokens_seen"] == 10
    assert validated["replay_evidence"]["evidence_score"] >= 0.80


def test_wallet_demotion_when_negative_replay_evidence_is_strong(tmp_path: Path):
    wallet = "wallet-demote"
    replay_records = [
        {"token_address": f"token-{idx}", "pnl_pct": -12.0, "hold_sec": 90, "wallet_hits": [wallet]}
        for idx in range(8)
    ]
    result = _run_eval(tmp_path, [_wallet_record(wallet, tier="tier_1", status="active", registry_score=0.9)], replay_records)
    validated = result["validated_registry"]["wallets"][0]
    assert validated["new_tier"] == "tier_2"
    assert validated["new_status"] == "watch"
    assert validated["promotion_decision"] == "demote"
    assert validated["replay_evidence"]["expectancy"] < 0


def test_sparse_evidence_produces_watch_pending_validation_not_rejection(tmp_path: Path):
    wallet = "wallet-sparse"
    replay_records = [
        {"token_address": f"token-{idx}", "pnl_pct": 9.0, "wallets": [wallet]}
        for idx in range(4)
    ]
    result = _run_eval(tmp_path, [_wallet_record(wallet, tier="tier_3")], replay_records)
    validated = result["validated_registry"]["wallets"][0]
    assert validated["new_tier"] == "tier_3"
    assert validated["new_status"] == "watch_pending_validation"
    assert validated["promotion_decision"] == "watch_pending_validation"


def test_deterministic_ordering_of_validated_outputs(tmp_path: Path):
    wallets = [
        _wallet_record("wallet-b", tier="tier_3", registry_score=0.75),
        _wallet_record("wallet-a", tier="tier_3", registry_score=0.70),
        _wallet_record("wallet-c", tier="tier_2", status="active", registry_score=0.95),
    ]
    replay_records = []
    replay_records.extend({"token_address": f"a-{idx}", "pnl_pct": 12.0, "wallets": ["wallet-a"]} for idx in range(5))
    replay_records.extend({"token_address": f"b-{idx}", "pnl_pct": 2.0, "wallets": ["wallet-b"]} for idx in range(5))
    replay_records.extend({"token_address": f"c-{idx}", "pnl_pct": -4.0, "wallets": ["wallet-c"]} for idx in range(5))
    result = _run_eval(tmp_path, wallets, replay_records)
    ordered_wallets = [record["wallet"] for record in result["validated_registry"]["wallets"]]
    assert ordered_wallets == ["wallet-a", "wallet-b", "wallet-c"]


def test_bounded_validated_hot_set(tmp_path: Path):
    wallets = [_wallet_record(f"wallet-{idx:02d}", tier="tier_3", registry_score=0.9 - idx * 0.01) for idx in range(6)]
    replay_records = []
    for idx in range(6):
        replay_records.extend(
            {"token_address": f"token-{idx}-{sample}", "pnl_pct": 10.0 + idx, "wallets": [f"wallet-{idx:02d}"]}
            for sample in range(5)
        )
    result = _run_eval(tmp_path, wallets, replay_records, max_hot=3)
    hot_wallets = result["validated_hot_wallets"]["wallets"]
    assert len(hot_wallets) == 3
    assert [record["wallet"] for record in hot_wallets] == ["wallet-05", "wallet-04", "wallet-03"]


def test_missing_replay_inputs_fails_clearly(tmp_path: Path):
    registry_path = _write_registry(tmp_path / "smart_wallets.json", [_wallet_record("wallet-a", tier="tier_3")])
    tmp_path.mkdir(parents=True, exist_ok=True)
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    with pytest.raises(ReplayInputError, match="No usable wallet-specific replay evidence found"):
        evaluate_wallet_registry_replay(
            registry_path=registry_path,
            processed_dir=processed_dir,
            out_report=tmp_path / "report.json",
            out_registry=tmp_path / "validated.json",
            out_hot=tmp_path / "hot.json",
            event_log=tmp_path / "events.jsonl",
            generated_at=FIXED_TS,
        )


def test_mixed_quality_replay_evidence_handled_gracefully(tmp_path: Path):
    wallets = [_wallet_record("wallet-a", tier="tier_3"), _wallet_record("wallet-b", tier="tier_2")]
    replay_records = [
        {"token_address": "token-1", "pnl_pct": 8.0, "wallets": ["wallet-a"]},
        {"token_address": "token-2", "smart_wallet_hit_count": 3, "pnl_pct": 20.0},
        {"token_address": "token-3", "pnl_pct": -6.0, "wallet_features": {"matched_wallets": ["wallet-b"]}},
        {"token_address": "token-4", "positive_outcome": True, "wallets": ["wallet-b"]},
    ]
    result = _run_eval(tmp_path, wallets, replay_records)
    report = result["report"]
    assert report["input_summary"]["wallet_specific_records"] == 3
    validated = {record["wallet"]: record for record in result["validated_registry"]["wallets"]}
    assert validated["wallet-a"]["promotion_decision"] == "watch_pending_validation"
    assert validated["wallet-b"]["promotion_decision"] in {"hold", "watch_pending_validation"}


def test_same_inputs_yield_deterministic_identical_outputs(tmp_path: Path):
    wallets = [_wallet_record("wallet-a", tier="tier_3"), _wallet_record("wallet-b", tier="tier_2", status="active")]
    replay_records = []
    replay_records.extend({"token_address": f"token-a-{idx}", "pnl_pct": 10.0, "wallets": ["wallet-a"]} for idx in range(5))
    replay_records.extend({"token_address": f"token-b-{idx}", "pnl_pct": 1.0, "wallets": ["wallet-b"]} for idx in range(10))

    first = _run_eval(tmp_path / "run1", wallets, replay_records)
    second = _run_eval(tmp_path / "run2", wallets, replay_records)

    assert first["report"] == second["report"]
    assert first["validated_registry"] == second["validated_registry"]
    assert first["validated_hot_wallets"] == second["validated_hot_wallets"]
