from __future__ import annotations

from data.tx_cache_policy import classify_tx_batch_freshness, resolve_tx_fetch_mode, should_refresh_tx_batch


def _batch(fetched_at: str, status: str = "usable") -> dict:
    return {
        "tx_batch_status": status,
        "tx_batch_fetched_at": fetched_at,
        "tx_batch_record_count": 1,
    }


def test_fresh_cache_is_reused_without_refresh():
    batch = _batch("2026-03-20T10:00:00Z")
    freshness = classify_tx_batch_freshness(batch, now_ts=1774001700, max_age_sec=900)
    assert freshness["freshness"] == "fresh_cache"
    assert should_refresh_tx_batch(batch, now_ts=1774001700, max_age_sec=900) is False
    assert resolve_tx_fetch_mode(batch, now_ts=1774001700, max_age_sec=900) == "fresh_cache"


def test_stale_cache_can_be_used_when_policy_allows_it():
    batch = _batch("2026-03-20T08:00:00Z")
    freshness = classify_tx_batch_freshness(batch, now_ts=1774001700, max_age_sec=900, stale_age_sec=20_000)
    assert freshness["freshness"] == "stale_cache_allowed"
    assert resolve_tx_fetch_mode(batch, now_ts=1774001700, max_age_sec=900, stale_age_sec=20_000, allow_stale=True) == "stale_cache_allowed"


def test_refresh_required_and_stale_fallback_are_distinguished():
    batch = _batch("2026-03-18T08:00:00Z")
    assert resolve_tx_fetch_mode(batch, now_ts=1774001700, max_age_sec=900, stale_age_sec=3_600, allow_stale=True) == "refresh_required"
    assert resolve_tx_fetch_mode(batch, now_ts=1774001700, max_age_sec=900, stale_age_sec=500_000, allow_stale=True, upstream_failed=True) == "upstream_failed_use_stale"


def test_missing_batch_is_reported_honestly():
    assert classify_tx_batch_freshness(None)["freshness"] == "missing"
    assert resolve_tx_fetch_mode(None) == "missing"
