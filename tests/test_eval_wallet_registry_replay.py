from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_eval_wallet_registry_replay_cli(tmp_path: Path):
    registry = {
        "contract_version": "smart_wallet_registry.v1",
        "generated_at": "2026-03-18T00:00:00Z",
        "input_summary": {"valid_wallets": 1},
        "registry_summary": {
            "total_candidates": 1,
            "kept_wallets": 1,
            "rejected_wallets": 0,
            "tier_1_count": 0,
            "tier_2_count": 0,
            "tier_3_count": 1,
            "active_count": 0,
            "watch_count": 1,
        },
        "wallets": [
            {
                "wallet": "wallet-cli",
                "status": "watch",
                "tier": "tier_3",
                "registry_score": 0.71,
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
                "watch_priority": 0.71,
                "hot_priority": 0.71,
                "added_at": "2026-03-18T00:00:00Z",
                "updated_at": "2026-03-18T00:00:00Z",
            }
        ],
    }
    registry_path = tmp_path / "smart_wallets.json"
    registry_path.write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    rows = [
        {"token_address": f"token-{idx}", "pnl_pct": 6.0, "wallets": ["wallet-cli"]}
        for idx in range(5)
    ]
    (processed_dir / "paper_trades.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    report = tmp_path / "replay_validation_report.json"
    validated_registry = tmp_path / "smart_wallets.validated.json"
    validated_hot = tmp_path / "hot_wallets.validated.json"
    events = tmp_path / "promotion_events.jsonl"

    subprocess.run(
        [
            sys.executable,
            "scripts/eval_wallet_registry_replay.py",
            "--registry",
            str(registry_path),
            "--processed-dir",
            str(processed_dir),
            "--out-report",
            str(report),
            "--out-registry",
            str(validated_registry),
            "--out-hot",
            str(validated_hot),
            "--event-log",
            str(events),
            "--generated-at",
            "2026-03-18T00:00:00Z",
        ],
        check=True,
    )

    assert report.exists()
    assert validated_registry.exists()
    assert validated_hot.exists()
    assert events.exists()

    validated = json.loads(validated_registry.read_text(encoding="utf-8"))
    wallet = validated["wallets"][0]
    assert wallet["wallet"] == "wallet-cli"
    assert wallet["promotion_decision"] == "promote"
    assert wallet["new_tier"] == "tier_2"
