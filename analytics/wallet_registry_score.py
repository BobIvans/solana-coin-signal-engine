"""Deterministic scoring helpers for the local smart wallet registry."""

from __future__ import annotations

from typing import Any

RECOGNIZED_TAG_SCORES: dict[str, float] = {
    "high_conviction": 0.30,
    "replay_winner": 0.25,
    "scalp_candidate": 0.15,
    "trend_candidate": 0.15,
    "tier1_hint": 0.10,
    "tier2_hint": 0.05,
    "manual_bulk": 0.00,
}
TAG_SCORE_CAP = 1.0
SOURCE_COUNT_CAP = 3

REGISTRY_SCORE_WEIGHTS: dict[str, float] = {
    "manual_priority": 0.45,
    "source_count": 0.20,
    "tag_quality": 0.15,
    "notes_quality": 0.10,
    "format_confidence": 0.10,
}

TIER_1_MIN_SCORE = 0.80
TIER_2_MIN_SCORE = 0.60
TIER_3_MIN_SCORE = 0.35
ACTIVE_MIN_SCORE = 0.60
DEFAULT_MAX_ACTIVE = 250
DEFAULT_MAX_WATCHLIST = 500
DEFAULT_MAX_HOT = 100

_TIER_RANK = {
    "tier_1": 0,
    "tier_2": 1,
    "tier_3": 2,
    "rejected": 3,
}
_STATUS_RANK = {
    "active": 0,
    "watch": 1,
    "rejected": 2,
}


def _unique_sorted_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    cleaned = {str(tag or "").strip().lower() for tag in (tags or []) if str(tag or "").strip()}
    return sorted(cleaned)


def manual_priority_score(manual_priority: bool) -> float:
    return 1.0 if manual_priority else 0.0


def source_count_score(source_count: int) -> float:
    bounded = max(0, min(int(source_count or 0), SOURCE_COUNT_CAP))
    return bounded / SOURCE_COUNT_CAP


def tag_quality_score(tags: list[str] | tuple[str, ...] | None) -> float:
    score = sum(RECOGNIZED_TAG_SCORES.get(tag, 0.0) for tag in _unique_sorted_tags(tags))
    return min(TAG_SCORE_CAP, score)


def notes_quality_score(notes: str | None) -> float:
    return 1.0 if str(notes or "").strip() else 0.0


def compute_regime_fit(tags: list[str] | tuple[str, ...] | None, notes: str | None) -> tuple[float, float]:
    normalized_tags = set(_unique_sorted_tags(tags))
    notes_text = str(notes or "").strip().lower()

    scalp = 0.20
    trend = 0.20

    if "scalp_candidate" in normalized_tags:
        scalp += 0.50
    if "trend_candidate" in normalized_tags:
        trend += 0.50
    if "replay_winner" in normalized_tags:
        scalp += 0.15
        trend += 0.15
    if "high_conviction" in normalized_tags:
        scalp += 0.10
        trend += 0.10
    if "scalp" in notes_text:
        scalp += 0.10
    if "trend" in notes_text:
        trend += 0.10

    return round(min(1.0, scalp), 6), round(min(1.0, trend), 6)


def compute_registry_score(
    *,
    manual_priority: bool,
    source_count: int,
    tags: list[str] | tuple[str, ...] | None,
    notes: str | None,
    format_confidence: float,
) -> float:
    score = (
        REGISTRY_SCORE_WEIGHTS["manual_priority"] * manual_priority_score(manual_priority)
        + REGISTRY_SCORE_WEIGHTS["source_count"] * source_count_score(source_count)
        + REGISTRY_SCORE_WEIGHTS["tag_quality"] * tag_quality_score(tags)
        + REGISTRY_SCORE_WEIGHTS["notes_quality"] * notes_quality_score(notes)
        + REGISTRY_SCORE_WEIGHTS["format_confidence"] * float(format_confidence)
    )
    return round(min(1.0, max(0.0, score)), 6)


def derive_watch_priority(record: dict[str, Any]) -> float:
    priority = float(record["registry_score"])
    if record.get("manual_priority"):
        priority += 0.15
    if record.get("quality_flags", {}).get("sparse_metadata"):
        priority += 0.05
    if "replay_winner" in set(record.get("tags", [])):
        priority += 0.05
    return round(priority, 6)


def derive_hot_priority(record: dict[str, Any]) -> float:
    tags = set(record.get("tags", []))
    priority = float(record["registry_score"])
    if "high_conviction" in tags:
        priority += 0.40
    if "replay_winner" in tags:
        priority += 0.30
    if "scalp_candidate" in tags:
        priority += 0.15
    if "trend_candidate" in tags:
        priority += 0.15
    if str(record.get("notes") or "").strip():
        priority += 0.05
    return round(priority, 6)


def qualifies_for_tier_1(record: dict[str, Any]) -> bool:
    tags = set(record.get("tags", []))
    return float(record.get("registry_score") or 0.0) >= TIER_1_MIN_SCORE and bool(tags & {"high_conviction", "replay_winner"})


def tier_sort_key(tier: str) -> int:
    return _TIER_RANK.get(str(tier), 99)


def status_sort_key(status: str) -> int:
    return _STATUS_RANK.get(str(status), 99)


__all__ = [
    "ACTIVE_MIN_SCORE",
    "DEFAULT_MAX_ACTIVE",
    "DEFAULT_MAX_HOT",
    "DEFAULT_MAX_WATCHLIST",
    "TIER_1_MIN_SCORE",
    "TIER_2_MIN_SCORE",
    "TIER_3_MIN_SCORE",
    "compute_regime_fit",
    "compute_registry_score",
    "derive_hot_priority",
    "derive_watch_priority",
    "qualifies_for_tier_1",
    "status_sort_key",
    "tag_quality_score",
    "tier_sort_key",
]
