from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from analytics.wallet_registry_bias import CONVICTION_BONUS_CAP, compute_wallet_registry_bias
from collectors.wallet_registry_loader import load_wallet_registry_lookup


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_wallet_registry_lookup_loads_validated_and_hot_wallets(tmp_path: Path):
    validated = tmp_path / "smart_wallets.validated.json"
    hot = tmp_path / "hot_wallets.validated.json"
    _write_json(
        validated,
        {
            "contract_version": "smart_wallet_registry_validated.v1",
            "wallets": [
                {"wallet": "hot1", "new_tier": "tier_1", "new_status": "active", "registry_score": 0.9},
                {"wallet": "watch1", "new_tier": "tier_3", "new_status": "watch_pending_validation", "registry_score": 0.4},
            ],
        },
    )
    _write_json(
        hot,
        {
            "contract_version": "hot_wallets_validated.v1",
            "wallets": [{"wallet": "hot1", "new_tier": "tier_1", "new_status": "active"}],
        },
    )

    lookup = load_wallet_registry_lookup(validated, hot)
    assert lookup["status"] == "validated"
    assert lookup["validated_size"] == 2
    assert lookup["hot_set_size"] == 1
    assert lookup["validated_wallets"]["hot1"]["is_hot"] is True
    assert lookup["validated_wallets"]["watch1"]["status"] == "watch_pending_validation"


def test_wallet_registry_lookup_missing_registry_degrades(tmp_path: Path):
    lookup = load_wallet_registry_lookup(tmp_path / "missing.validated.json", tmp_path / "missing.hot.json")
    assert lookup["status"] == "degraded_missing_registry"
    assert lookup["validated_size"] == 0
    assert lookup["hot_set_size"] == 0


def test_wallet_registry_lookup_empty_registry_degrades(tmp_path: Path):
    validated = tmp_path / "smart_wallets.validated.json"
    _write_json(validated, {"contract_version": "smart_wallet_registry_validated.v1", "wallets": []})
    lookup = load_wallet_registry_lookup(validated, tmp_path / "hot_wallets.validated.json")
    assert lookup["status"] == "degraded_empty_registry"
    assert lookup["validated_size"] == 0


def test_wallet_registry_bias_counts_are_deterministic_and_capped():
    lookup = {
        "status": "validated",
        "validated_size": 4,
        "hot_set_size": 3,
        "validated_wallets": {
            "hot1": {"wallet": "hot1", "tier": "tier_1", "status": "active", "is_hot": True, "early_entry_positive": False},
            "hot2": {"wallet": "hot2", "tier": "tier_2", "status": "active", "is_hot": True, "early_entry_positive": True},
            "watch1": {"wallet": "watch1", "tier": "tier_3", "status": "watch_pending_validation", "is_hot": False, "early_entry_positive": False},
            "watch2": {"wallet": "watch2", "tier": "tier_3", "status": "watch", "is_hot": True, "early_entry_positive": False},
        },
    }
    first = compute_wallet_registry_bias(["watch1", "hot1", "hot2", "hot1", "watch2"], lookup)
    second = compute_wallet_registry_bias(["watch2", "hot2", "hot1", "watch1"], lookup)

    assert first == second
    assert first["smart_wallet_score_sum"] == 1.8
    assert first["smart_wallet_tier1_hits"] == 1
    assert first["smart_wallet_tier2_hits"] == 1
    assert first["smart_wallet_tier3_hits"] == 2
    assert first["smart_wallet_early_entry_hits"] == 1
    assert first["smart_wallet_active_hits"] == 2
    assert first["smart_wallet_watch_hits"] == 2
    assert first["smart_wallet_registry_confidence"] == "high"
    assert first["smart_wallet_conviction_bonus"] <= CONVICTION_BONUS_CAP
    assert first["smart_wallet_netflow_bias"] is None
    assert first["smart_wallet_dispersion_score"] > 0
