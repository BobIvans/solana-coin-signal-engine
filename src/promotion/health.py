from __future__ import annotations

from typing import Any


_RUNTIME_HEALTH_CONTRACT_VERSION = "runtime_health.v1"


def _safe_div(n: float, d: float) -> float:
    return 0.0 if d == 0 else n / d


def build_runtime_health_summary(
    *,
    run_id: str,
    mode: str,
    runtime_metrics: dict[str, Any] | None = None,
    degraded_x_runtime: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    artifact_manifest_path: str | None = None,
) -> dict[str, Any]:
    runtime_metrics = dict(runtime_metrics or {})
    degraded_x_runtime = dict(degraded_x_runtime or {})
    summary = dict(summary or {})

    live = int(runtime_metrics.get("runtime_current_state_live_count", 0) or 0)
    fallback = int(runtime_metrics.get("runtime_current_state_fallback_count", 0) or 0)
    stale = int(runtime_metrics.get("runtime_current_state_stale_count", 0) or 0)
    refresh_failed = int(runtime_metrics.get("runtime_current_state_refresh_failed_count", 0) or 0)
    current_state_total = live + fallback + stale + refresh_failed

    degraded_attempted = int(degraded_x_runtime.get("degraded_entries_attempted", 0) or 0)
    degraded_opened = int(degraded_x_runtime.get("degraded_entries_opened", 0) or 0)
    degraded_blocked = int(degraded_x_runtime.get("degraded_entries_blocked", 0) or 0)

    tx_partial = int(summary.get("tx_window_partial_count", runtime_metrics.get("tx_window_partial_count", 0)) or 0)
    tx_truncated = int(summary.get("tx_window_truncated_count", runtime_metrics.get("tx_window_truncated_count", 0)) or 0)
    partial_evidence = int(summary.get("partial_evidence_entry_count", runtime_metrics.get("partial_evidence_entry_count", 0)) or 0)
    unresolved_replay = int(summary.get("unresolved_replay_row_count", runtime_metrics.get("unresolved_replay_row_count", 0)) or 0)
    fallback_refresh_failure = int(summary.get("fallback_refresh_failure_count", refresh_failed) or 0)
    x_cooldown_skip_count = int(summary.get("x_cooldown_skip_count", runtime_metrics.get("x_cooldown_skip_count", 0)) or 0)
    runtime_market_cache_pruned_count = int(summary.get("runtime_market_cache_pruned_count", runtime_metrics.get("runtime_market_cache_pruned_count", 0)) or 0)
    runtime_market_cache_size = int(summary.get("runtime_market_cache_size", runtime_metrics.get("runtime_market_cache_size", 0)) or 0)
    runtime_market_cache_pinned_count = int(summary.get("runtime_market_cache_pinned_count", runtime_metrics.get("runtime_market_cache_pinned_count", 0)) or 0)

    warnings: list[str] = []
    if stale > 0:
        warnings.append("runtime_current_state_stale_present")
    if refresh_failed > 0:
        warnings.append("runtime_current_state_refresh_failures_present")
    if summary.get("degraded_x_budget_active"):
        warnings.append("degraded_x_budget_active")
    if summary.get("x_cooldown_active"):
        warnings.append("x_cooldown_active")

    return {
        "contract_version": _RUNTIME_HEALTH_CONTRACT_VERSION,
        "run_id": run_id,
        "mode": mode,
        "runtime_current_state_live_count": live,
        "runtime_current_state_fallback_count": fallback,
        "runtime_current_state_stale_count": stale,
        "runtime_current_state_refresh_failed_count": refresh_failed,
        "runtime_current_state_stale_rate": _safe_div(stale, current_state_total),
        "runtime_current_state_fallback_rate": _safe_div(fallback, current_state_total),
        "runtime_current_state_live_rate": _safe_div(live, current_state_total),
        "degraded_x_entries_attempted": degraded_attempted,
        "degraded_x_entries_opened": degraded_opened,
        "degraded_x_entries_blocked": degraded_blocked,
        "degraded_x_block_rate": _safe_div(degraded_blocked, degraded_attempted),
        "degraded_x_budget_active": bool(summary.get("degraded_x_budget_active", False)),
        "x_cooldown_active": bool(summary.get("x_cooldown_active", False)),
        "tx_window_partial_count": tx_partial,
        "tx_window_truncated_count": tx_truncated,
        "partial_evidence_entry_count": partial_evidence,
        "unresolved_replay_row_count": unresolved_replay,
        "fallback_refresh_failure_count": fallback_refresh_failure,
        "x_cooldown_skip_count": x_cooldown_skip_count,
        "runtime_market_cache_pruned_count": runtime_market_cache_pruned_count,
        "runtime_market_cache_size": runtime_market_cache_size,
        "runtime_market_cache_pinned_count": runtime_market_cache_pinned_count,
        "http_session_enabled": bool(summary.get("http_session_enabled", True)),
        "artifact_manifest_path": artifact_manifest_path or summary.get("artifact_manifest_path", ""),
        "warnings": warnings,
    }
