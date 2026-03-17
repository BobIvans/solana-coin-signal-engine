from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)

from src.wallets.registry import build_wallet_registry, deduplicate_wallets


def test_registry_build_deterministic():
    records = [
        {"wallet_address": "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty", "source": "a", "tier": "tier_1", "score": 0.5, "status": "active"},
        {"wallet_address": "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty", "source": "b", "tier": "tier_2", "score": 0.7, "status": "active"},
    ]
    cfg = {"registry": {"deduplicate": True}}
    first, _ = build_wallet_registry(records, cfg)
    second, _ = build_wallet_registry(records, cfg)
    assert first == second


def test_deduplication_correct():
    out = deduplicate_wallets([
        {"wallet_address": "w", "source": "a", "score": 0.1, "tier": "tier_3"},
        {"wallet_address": "w", "source": "b", "score": 0.4, "tier": "tier_1"},
    ])
    assert out[0]["score"] == 0.4
    assert out[0]["sources"] == ["a", "b"]


def test_tier_normalization_correct():
    out, _ = build_wallet_registry([
        {"wallet_address": "4Nd1mYwJ8M4d4R9vYj4M5Hn5QZQqNf8QjF2bU8X2h7Ty", "source": "a", "tier": "T2", "score": 0.4, "status": "active"}
    ], {"registry": {}})
    assert out[0]["tier"] == "tier_2"
