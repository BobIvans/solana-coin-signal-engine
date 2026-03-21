from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_promotion_loop.py"
spec = importlib.util.spec_from_file_location("run_promotion_loop", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_prune_removes_entries_older_than_ttl_when_unpinned():
    state = {
        "runtime_market_state_cache": {
            "STALE": {"token_address": "STALE", "cached_at": "2000-01-01T00:00:00+00:00"},
            "LIVE": {"token_address": "LIVE", "cached_at": "2099-01-01T00:00:00+00:00"},
        },
        "positions": [],
    }
    market_states = [{"token_address": "LIVE", "now_ts": "2099-01-01T00:00:00+00:00"}]

    summary = module._prune_runtime_market_state_cache(
        state,
        market_states,
        max_cache_age_sec=3600,
        max_cache_entries=100,
    )

    assert len(summary.get("removed_tokens", [])) >= 1
    assert "STALE" not in state["runtime_market_state_cache"]
    assert "LIVE" in state["runtime_market_state_cache"]


def test_prune_respects_max_entries_cap():
    state = {
        "runtime_market_state_cache": {
            "A": {"token_address": "A", "cached_at": "2026-03-20T00:00:00+00:00"},
            "B": {"token_address": "B", "cached_at": "2026-03-20T00:00:01+00:00"},
            "C": {"token_address": "C", "cached_at": "2026-03-20T00:00:02+00:00"},
        },
        "positions": [],
    }
    market_states = []

    summary = module._prune_runtime_market_state_cache(
        state,
        market_states,
        max_cache_age_sec=10**9,
        max_cache_entries=2,
    )

    assert len(summary.get("removed_tokens", [])) >= 1
    assert len(state["runtime_market_state_cache"]) <= 2


def test_prune_never_removes_open_position_cache_entries():
    state = {
        "runtime_market_state_cache": {
            "PINNED": {"token_address": "PINNED", "cached_at": "2000-01-01T00:00:00+00:00"},
            "DROP": {"token_address": "DROP", "cached_at": "2000-01-01T00:00:00+00:00"},
        },
        "positions": [
            {"token_address": "PINNED", "is_open": True},
        ],
    }
    market_states = []

    summary = module._prune_runtime_market_state_cache(
        state,
        market_states,
        max_cache_age_sec=3600,
        max_cache_entries=1,
    )

    assert "PINNED" in state["runtime_market_state_cache"]
    assert int(summary.get("runtime_market_cache_pinned_count", 0)) >= 1
