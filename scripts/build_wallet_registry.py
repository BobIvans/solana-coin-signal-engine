#!/usr/bin/env python3
"""Build deterministic wallet registry artifacts from normalized manual wallet seeds."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from analytics.wallet_registry_score import (
    ACTIVE_MIN_SCORE,
    DEFAULT_MAX_ACTIVE,
    DEFAULT_MAX_HOT,
    DEFAULT_MAX_WATCHLIST,
    TIER_2_MIN_SCORE,
    TIER_3_MIN_SCORE,
    compute_regime_fit,
    compute_registry_score,
    derive_hot_priority,
    derive_watch_priority,
    qualifies_for_tier_1,
    status_sort_key,
    tier_sort_key,
)
from collectors.wallet_registry_loader import load_normalized_wallet_candidates
from utils.clock import utc_now_iso
from utils.io import append_jsonl, ensure_dir, write_json

REGISTRY_CONTRACT_VERSION = "smart_wallet_registry.v1"
WATCHLIST_CONTRACT_VERSION = "active_watchlist.v1"
HOT_WALLETS_CONTRACT_VERSION = "hot_wallets.v1"


def _is_sparse_manual_seed(record: dict[str, Any]) -> bool:
    flags = record.get("quality_flags", {})
    return bool(record.get("manual_priority")) and bool(flags.get("sparse_metadata"))


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _classify_wallet(record: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    quality_flags = dict(record.get("quality_flags", {}))
    format_confidence = float(record.get("format_confidence") or 0.0)

    if format_confidence <= 0.0:
        _append_reason(reasons, "rejected_invalid_wallet")
        registry_score = 0.0
        regime_scalp, regime_trend = 0.0, 0.0
        return {
            **record,
            "status": "rejected",
            "tier": "rejected",
            "registry_score": registry_score,
            "filter_reasons": reasons,
            "quality_flags": quality_flags,
            "regime_fit_scalp": regime_scalp,
            "regime_fit_trend": regime_trend,
            "watch_priority": 0.0,
            "hot_priority": 0.0,
        }

    registry_score = compute_registry_score(
        manual_priority=bool(record.get("manual_priority")),
        source_count=int(record.get("source_count") or 0),
        tags=record.get("tags") or [],
        notes=record.get("notes"),
        format_confidence=format_confidence,
    )
    regime_scalp, regime_trend = compute_regime_fit(record.get("tags") or [], record.get("notes"))

    if record.get("manual_priority"):
        _append_reason(reasons, "kept_manual_seed")
    if _is_sparse_manual_seed(record):
        _append_reason(reasons, "watch_due_to_low_metadata")

    if qualifies_for_tier_1({**record, "registry_score": registry_score}):
        tier = "tier_1"
    elif _is_sparse_manual_seed(record):
        tier = "tier_3"
    elif registry_score >= TIER_2_MIN_SCORE:
        tier = "tier_2"
    elif registry_score >= TIER_3_MIN_SCORE:
        tier = "tier_3"
    else:
        tier = "rejected"
        _append_reason(reasons, "rejected_low_confidence")

    status = "watch"
    if tier == "rejected":
        status = "rejected"
    elif _is_sparse_manual_seed(record):
        status = "watch"
    elif registry_score >= ACTIVE_MIN_SCORE and tier in {"tier_1", "tier_2", "tier_3"}:
        status = "active"
        _append_reason(reasons, "active_due_to_score")

    if tier == "tier_1" and "active_due_to_score" not in reasons:
        _append_reason(reasons, "active_due_to_score")

    scored = {
        **record,
        "status": status,
        "tier": tier,
        "registry_score": registry_score,
        "filter_reasons": reasons,
        "quality_flags": quality_flags,
        "regime_fit_scalp": regime_scalp,
        "regime_fit_trend": regime_trend,
    }
    scored["watch_priority"] = derive_watch_priority(scored)
    scored["hot_priority"] = derive_hot_priority(scored)
    return scored


def _registry_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        status_sort_key(record["status"]),
        tier_sort_key(record["tier"]),
        -float(record["registry_score"]),
        -float(record["watch_priority"]),
        record["wallet"],
    )


def _watch_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        status_sort_key(record["status"]),
        -float(record["watch_priority"]),
        -float(record["registry_score"]),
        record["wallet"],
    )


def _hot_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tier_sort_key(record["tier"]),
        -float(record["hot_priority"]),
        -float(record["registry_score"]),
        record["wallet"],
    )


def _record_event_payload(record: dict[str, Any], generated_at: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    reasons = record.get("filter_reasons") or ["classified"]
    for reason in reasons:
        events.append(
            {
                "wallet": record["wallet"],
                "event_type": "wallet_registry_filter",
                "reason": reason,
                "old_status": record.get("input_status"),
                "new_status": record.get("status"),
                "score": record.get("registry_score"),
                "timestamp": generated_at,
            }
        )
    return events


def _finalize_statuses(records: list[dict[str, Any]], *, max_active: int) -> list[dict[str, Any]]:
    eligible = [record for record in records if record["status"] != "rejected" and float(record["registry_score"]) >= ACTIVE_MIN_SCORE]
    active_wallets = {
        record["wallet"]
        for record in sorted(eligible, key=_watch_sort_key)[: max(0, max_active)]
    }

    finalized: list[dict[str, Any]] = []
    for record in records:
        updated = dict(record)
        reasons = list(updated.get("filter_reasons", []))
        if updated["status"] != "rejected":
            updated["status"] = "active" if updated["wallet"] in active_wallets and not _is_sparse_manual_seed(updated) else "watch"
            if updated["status"] == "active":
                _append_reason(reasons, "active_due_to_score")
        updated["filter_reasons"] = reasons
        updated["watch_priority"] = derive_watch_priority(updated)
        updated["hot_priority"] = derive_hot_priority(updated)
        finalized.append(updated)
    return sorted(finalized, key=_registry_sort_key)


def _registry_summary(records: list[dict[str, Any]], total_candidates: int) -> dict[str, int]:
    return {
        "total_candidates": total_candidates,
        "kept_wallets": sum(1 for record in records if record["status"] != "rejected"),
        "rejected_wallets": sum(1 for record in records if record["status"] == "rejected"),
        "tier_1_count": sum(1 for record in records if record["tier"] == "tier_1"),
        "tier_2_count": sum(1 for record in records if record["tier"] == "tier_2"),
        "tier_3_count": sum(1 for record in records if record["tier"] == "tier_3"),
        "active_count": sum(1 for record in records if record["status"] == "active"),
        "watch_count": sum(1 for record in records if record["status"] == "watch"),
    }


def build_registry_artifacts(
    in_path: str | Path,
    *,
    generated_at: str | None = None,
    max_watchlist: int = DEFAULT_MAX_WATCHLIST,
    max_hot: int = DEFAULT_MAX_HOT,
    max_active: int = DEFAULT_MAX_ACTIVE,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    loaded = load_normalized_wallet_candidates(in_path)
    timestamp = generated_at or str(loaded.get("generated_at") or utc_now_iso())

    classified = [_classify_wallet(record) for record in loaded["candidates"]]
    finalized = _finalize_statuses(classified, max_active=min(max_active, max_watchlist))
    for record in finalized:
        record["added_at"] = str(record.get("imported_at") or timestamp)
        record["updated_at"] = timestamp

    watch_wallets = sorted(
        [record for record in finalized if record["status"] in {"active", "watch"}],
        key=_watch_sort_key,
    )[: max(0, max_watchlist)]
    hot_wallets = sorted(
        [record for record in finalized if record["status"] == "active" and record["tier"] != "rejected"],
        key=_hot_sort_key,
    )[: max(0, max_hot)]

    registry_payload = {
        "contract_version": REGISTRY_CONTRACT_VERSION,
        "generated_at": timestamp,
        "input_summary": loaded.get("input_summary") or {},
        "registry_summary": _registry_summary(finalized, len(loaded["candidates"])),
        "wallets": finalized,
    }
    watch_payload = {
        "contract_version": WATCHLIST_CONTRACT_VERSION,
        "generated_at": timestamp,
        "watchlist_summary": {
            "max_watchlist_size": max_watchlist,
            "selected_wallets": len(watch_wallets),
            "active_wallets": sum(1 for record in watch_wallets if record["status"] == "active"),
            "watch_wallets": sum(1 for record in watch_wallets if record["status"] == "watch"),
        },
        "wallets": watch_wallets,
    }
    hot_payload = {
        "contract_version": HOT_WALLETS_CONTRACT_VERSION,
        "generated_at": timestamp,
        "hot_summary": {
            "max_hot_wallets_size": max_hot,
            "selected_wallets": len(hot_wallets),
            "tier_1_wallets": sum(1 for record in hot_wallets if record["tier"] == "tier_1"),
            "tier_2_wallets": sum(1 for record in hot_wallets if record["tier"] == "tier_2"),
            "tier_3_wallets": sum(1 for record in hot_wallets if record["tier"] == "tier_3"),
        },
        "wallets": hot_wallets,
    }
    events = []
    for record in finalized:
        events.extend(_record_event_payload(record, timestamp))
    return registry_payload, watch_payload, hot_payload, events


def write_registry_artifacts(
    *,
    registry_payload: dict[str, Any],
    watch_payload: dict[str, Any],
    hot_payload: dict[str, Any],
    events: list[dict[str, Any]],
    out_path: str | Path,
    watch_out_path: str | Path,
    hot_out_path: str | Path,
    event_log_path: str | Path,
) -> None:
    write_json(out_path, registry_payload)
    write_json(watch_out_path, watch_payload)
    write_json(hot_out_path, hot_payload)
    event_target = Path(event_log_path).expanduser().resolve()
    ensure_dir(event_target.parent)
    if not event_target.exists():
        event_target.write_text("", encoding="utf-8")
    for event in events:
        append_jsonl(event_target, event)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="data/registry/normalized_wallet_candidates.json")
    parser.add_argument("--out", dest="out_path", default="data/registry/smart_wallets.json")
    parser.add_argument("--watch-out", dest="watch_out_path", default="data/registry/active_watchlist.json")
    parser.add_argument("--hot-out", dest="hot_out_path", default="data/registry/hot_wallets.json")
    parser.add_argument("--event-log", dest="event_log_path", default="data/registry/filter_events.jsonl")
    parser.add_argument("--max-watchlist", type=int, default=DEFAULT_MAX_WATCHLIST)
    parser.add_argument("--max-hot", type=int, default=DEFAULT_MAX_HOT)
    parser.add_argument("--max-active", type=int, default=DEFAULT_MAX_ACTIVE)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_payload, watch_payload, hot_payload, events = build_registry_artifacts(
        args.in_path,
        generated_at=args.generated_at,
        max_watchlist=args.max_watchlist,
        max_hot=args.max_hot,
        max_active=args.max_active,
    )
    write_registry_artifacts(
        registry_payload=registry_payload,
        watch_payload=watch_payload,
        hot_payload=hot_payload,
        events=events,
        out_path=args.out_path,
        watch_out_path=args.watch_out_path,
        hot_out_path=args.hot_out_path,
        event_log_path=args.event_log_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
