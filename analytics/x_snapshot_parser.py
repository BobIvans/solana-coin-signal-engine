"""Parse raw X query snapshots and aggregate token-level validation metrics."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from analytics.short_horizon_signals import compute_x_author_velocity_5m
from utils.clock import utc_now_iso

_COUNTER_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([KMB])?$", re.IGNORECASE)
_CONTRACT_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_PUNCT_RE = re.compile(r"([!?.,])\1+")
_SPACE_RE = re.compile(r"\s+")


def _parse_counter(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper().replace(",", "")
    if not text:
        return 0.0
    match = _COUNTER_RE.match(text)
    if not match:
        return 0.0
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix == "K":
        return number * 1_000
    if suffix == "M":
        return number * 1_000_000
    if suffix == "B":
        return number * 1_000_000_000
    return number


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    lowered = _CONTRACT_RE.sub("", lowered)
    lowered = re.sub(r"\$[a-z0-9_]+", "", lowered)
    lowered = _PUNCT_RE.sub(r"\1", lowered)
    lowered = _SPACE_RE.sub(" ", lowered).strip()
    return lowered


def parse_query_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    cards = list(raw.get("cards", []) or [])
    parsed_cards: list[dict[str, Any]] = []
    for idx, card in enumerate(cards, start=1):
        engagement = card.get("engagement", {}) or {}
        text = str(card.get("text", "") or "")
        parsed_cards.append(
            {
                "author_handle": str(card.get("author_handle", "") or ""),
                "author_display": str(card.get("author_display", "") or ""),
                "text": text,
                "normalized_text": _normalize_text(text),
                "is_reply": bool(card.get("is_reply", False)),
                "is_repost": bool(card.get("is_repost", False)),
                "has_contract_mention": bool(card.get("has_contract_mention", False)) or bool(_CONTRACT_RE.search(text)),
                "engagement": {
                    "replies": _parse_counter(engagement.get("replies")),
                    "reposts": _parse_counter(engagement.get("reposts")),
                    "likes": _parse_counter(engagement.get("likes")),
                    "views": _parse_counter(engagement.get("views")),
                },
                "created_at": card.get("created_at"),
                "posted_at": card.get("posted_at"),
                "published_at": card.get("published_at"),
                "timestamp": card.get("timestamp"),
                "tweet_created_at": card.get("tweet_created_at"),
                "captured_rank": int(card.get("captured_rank", idx) or idx),
            }
        )

    return {**raw, "cards": parsed_cards, "posts_visible": len(parsed_cards)}


def aggregate_token_snapshots(token: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = [parse_query_snapshot(snapshot) for snapshot in snapshots]

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    fallback_seen: set[tuple[str, int, str]] = set()
    contract = str(token.get("token_address", "") or "")
    symbol = str(token.get("symbol", "") or "").upper()
    name = str(token.get("name", "") or "").lower()

    all_norm_texts: list[str] = []
    total_engagement = 0.0
    author_engagement: Counter[str] = Counter()

    statuses = [p.get("x_status", "error") for p in parsed]
    ok_count = sum(1 for status in statuses if status in {"ok", "empty"})

    for snapshot in parsed:
        for card in snapshot.get("cards", []):
            author = str(card.get("author_handle", "") or "")
            norm_text = str(card.get("normalized_text", "") or "")
            primary_key = (author, norm_text)
            fallback_key = (author, int(card.get("captured_rank", 0) or 0), norm_text[:80])
            if primary_key in deduped or fallback_key in fallback_seen:
                continue
            fallback_seen.add(fallback_key)
            deduped[primary_key] = card

            all_norm_texts.append(norm_text)
            eng = card.get("engagement", {})
            weighted = float(eng.get("likes", 0.0)) + 2 * float(eng.get("reposts", 0.0)) + 1.5 * float(eng.get("replies", 0.0)) + 0.02 * float(eng.get("views", 0.0))
            total_engagement += weighted
            author_engagement[author] += weighted

    cards = list(deduped.values())
    post_count = len(cards)
    unique_authors = sorted({str(card.get("author_handle", "") or "") for card in cards if card.get("author_handle")})

    duplicates = post_count - len(set(all_norm_texts))
    duplicate_ratio = (duplicates / post_count) if post_count else 0.0

    top_author_engagement = author_engagement.most_common(1)[0][1] if author_engagement else 0.0
    promoter_concentration = (top_author_engagement / total_engagement) if total_engagement > 0 else 0.0

    official_match = 0
    for handle in unique_authors:
        h = handle.lower().lstrip("@")
        if symbol and symbol.lower() in h:
            official_match = 1
            break
        if name and any(part for part in name.split() if len(part) > 3 and part in h):
            official_match = 1
            break

    contract_mention_presence = 1 if any(card.get("has_contract_mention", False) or contract in str(card.get("text", "")) for card in cards) else 0

    status = "ok"
    if parsed and all(s in {"timeout", "captcha", "login_required", "blocked", "degraded", "error"} for s in statuses):
        status = "degraded"

    cache_hit = any(bool(snapshot.get("cache_hit", False)) for snapshot in parsed)

    return {
        "token_address": contract,
        "symbol": str(token.get("symbol", "") or ""),
        "name": str(token.get("name", "") or ""),
        "x_posts_visible": post_count,
        "x_unique_authors_visible": len(unique_authors),
        "x_weighted_engagement": round(total_engagement, 4),
        "x_duplicate_text_ratio": round(duplicate_ratio, 4),
        "x_promoter_concentration": round(promoter_concentration, 4),
        "x_official_account_match": official_match,
        "x_contract_mention_presence": contract_mention_presence,
        "x_status": status,
        "x_queries_attempted": len(parsed),
        "x_queries_succeeded": ok_count,
        "x_cache_hit": cache_hit,
        "x_snapshot_at": utc_now_iso(),
        "x_author_velocity_5m": compute_x_author_velocity_5m(parsed),
    }
