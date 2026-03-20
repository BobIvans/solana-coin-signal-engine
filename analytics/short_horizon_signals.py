"""Deterministic short-horizon continuation metric helpers.

This module intentionally stays focused on pure feature computation.
Continuation orchestration, provenance, and fallback handling live in
`analytics.continuation_enricher`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import log
from typing import Any

from analytics.wallet_clustering import resolve_wallet_cluster_assignments

_SHORT_WINDOW_60S = 60
_SHORT_WINDOW_120S = 120
_X_WINDOW_5M = 300
_MIN_LIQUIDITY_SHOCK_RATIO = 0.10


def _parse_ts(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _window_transactions(txs: list[dict[str, Any]], start_ts: int, window_sec: int) -> list[dict[str, Any]]:
    if start_ts <= 0:
        return []
    out: list[dict[str, Any]] = []
    for tx in txs:
        ts = _parse_ts(tx.get("timestamp") or tx.get("blockTime") or tx.get("time") or tx.get("slot_time"))
        if start_ts <= ts <= start_ts + window_sec:
            out.append({**tx, "_parsed_ts": ts})
    out.sort(key=lambda item: (int(item.get("_parsed_ts") or 0), str(item.get("signature") or "")))
    return out


def _normalize_wallet(value: Any) -> str | None:
    if value is None:
        return None
    wallet = str(value).strip()
    return wallet or None


def _iter_token_transfers(tx: dict[str, Any]) -> list[dict[str, Any]]:
    transfers = tx.get("tokenTransfers")
    return [item for item in transfers if isinstance(item, dict)] if isinstance(transfers, list) else []


def _transfer_amount(transfer: dict[str, Any]) -> float | None:
    for key in ("tokenAmount", "amount", "uiAmount", "token_amount"):
        value = transfer.get(key)
        if value in (None, ""):
            continue
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return amount
    return None


def compute_net_unique_buyers_60s(*, pair_created_ts: int, txs: list[dict[str, Any]]) -> int | None:
    buyers: set[str] = set()
    sellers: set[str] = set()
    saw_side_evidence = False

    for tx in _window_transactions(txs, pair_created_ts, _SHORT_WINDOW_60S):
        for transfer in _iter_token_transfers(tx):
            amount = _transfer_amount(transfer)
            if amount is None:
                continue
            buyer = _normalize_wallet(transfer.get("toUserAccount") or transfer.get("toUser") or transfer.get("buyer"))
            seller = _normalize_wallet(transfer.get("fromUserAccount") or transfer.get("fromUser") or transfer.get("seller"))
            if buyer:
                buyers.add(buyer)
                saw_side_evidence = True
            if seller:
                sellers.add(seller)
                saw_side_evidence = True

    if not saw_side_evidence:
        return None
    return len(buyers) - len(sellers)


def _extract_liquidity_point(tx: dict[str, Any]) -> tuple[int, float] | None:
    ts = int(tx.get("_parsed_ts") or _parse_ts(tx.get("timestamp") or tx.get("blockTime") or tx.get("time")))
    if ts <= 0:
        return None

    candidates: list[Any] = [
        tx.get("liquidity_usd"),
        tx.get("liquidityUsd"),
        tx.get("pool_liquidity_usd"),
        tx.get("poolLiquidityUsd"),
        tx.get("post_liquidity_usd"),
        tx.get("postLiquidityUsd"),
        tx.get("liquidity"),
        (tx.get("liquidity_state") or {}).get("liquidity_usd") if isinstance(tx.get("liquidity_state"), dict) else None,
        (tx.get("liquidity_state") or {}).get("liquidityUsd") if isinstance(tx.get("liquidity_state"), dict) else None,
        (tx.get("pool_state") or {}).get("liquidity_usd") if isinstance(tx.get("pool_state"), dict) else None,
        (tx.get("pool_state") or {}).get("liquidityUsd") if isinstance(tx.get("pool_state"), dict) else None,
    ]

    for value in candidates:
        if isinstance(value, dict):
            for nested_key in ("usd", "liquidity_usd", "liquidityUsd", "value"):
                nested = value.get(nested_key)
                if nested in (None, ""):
                    continue
                try:
                    number = float(nested)
                except (TypeError, ValueError):
                    continue
                if number >= 0:
                    return ts, number
            continue
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return ts, number
    return None


def _liquidity_points_120s(*, pair_created_ts: int, txs: list[dict[str, Any]]) -> list[tuple[int, float]]:
    points: dict[int, float] = {}
    for tx in _window_transactions(txs, pair_created_ts, _SHORT_WINDOW_120S):
        point = _extract_liquidity_point(tx)
        if point is None:
            continue
        ts, liquidity = point
        points[ts] = liquidity
    return sorted(points.items())


def compute_liquidity_refill_ratio_120s(*, pair_created_ts: int, txs: list[dict[str, Any]]) -> float | None:
    points = _liquidity_points_120s(pair_created_ts=pair_created_ts, txs=txs)
    if len(points) < 2:
        return None

    baseline = points[0][1]
    min_ts, post_shock_min = min(points[1:], key=lambda item: (item[1], item[0]), default=points[0])
    if baseline <= 0 or post_shock_min >= baseline:
        return None

    recovered = max((value for ts, value in points if ts >= min_ts), default=post_shock_min)
    denominator = baseline - post_shock_min
    if denominator <= 0:
        return None
    return round((recovered - post_shock_min) / denominator, 6)


def _participant_records(txs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tx in txs:
        participants = tx.get("participants")
        if not isinstance(participants, list):
            continue
        for participant in participants:
            if isinstance(participant, dict):
                records.append(participant)
    return records


def compute_cluster_sell_concentration_120s(
    *,
    pair_created_ts: int,
    txs: list[dict[str, Any]],
    creator_wallet: str | None = None,
) -> float | None:
    window_txs = _window_transactions(txs, pair_created_ts, _SHORT_WINDOW_120S)
    participants = _participant_records(window_txs)
    if not participants:
        return None

    resolved = resolve_wallet_cluster_assignments(
        participants,
        creator_wallet=creator_wallet,
    )
    cluster_ids_by_wallet = resolved["cluster_ids_by_wallet"]
    if not cluster_ids_by_wallet:
        return None

    total_sell_volume = 0.0
    cluster_sell_volume: dict[str, float] = defaultdict(float)
    uncovered_volume = 0.0
    for tx in window_txs:
        for transfer in _iter_token_transfers(tx):
            seller = _normalize_wallet(transfer.get("fromUserAccount") or transfer.get("fromUser") or transfer.get("seller"))
            amount = _transfer_amount(transfer)
            if not seller or amount is None:
                continue
            total_sell_volume += amount
            cluster_id = cluster_ids_by_wallet.get(seller)
            if cluster_id:
                cluster_sell_volume[cluster_id] += amount
            else:
                uncovered_volume += amount

    if total_sell_volume <= 0 or not cluster_sell_volume:
        return None
    if uncovered_volume >= total_sell_volume * 0.5:
        return None
    return round(max(cluster_sell_volume.values()) / total_sell_volume, 6)


def _normalize_bucket(value: Any, prefix: str) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    return f"{prefix}:{normalized}" if normalized else None


def compute_smart_wallet_dispersion_score(
    hit_wallets: list[str] | tuple[str, ...] | None,
    wallet_lookup: dict[str, Any],
) -> float | None:
    registry = wallet_lookup.get("validated_wallets") or {}
    matched_records = [registry[wallet] for wallet in sorted({str(wallet or "").strip() for wallet in (hit_wallets or []) if str(wallet or "").strip()}) if wallet in registry]
    if not matched_records:
        return None

    dimensions: list[list[str]] = []
    tiers = [_normalize_bucket(record.get("tier"), "tier") for record in matched_records]
    dimensions.append([value for value in tiers if value])

    family_values = []
    for record in matched_records:
        family = None
        for key in ("independent_family", "family_id", "family", "cluster_family", "wallet_family"):
            family = record.get(key)
            if family not in (None, ""):
                break
        family_values.append(_normalize_bucket(family, "family"))
    if any(family_values):
        dimensions.append([value for value in family_values if value])

    cluster_values = []
    for record in matched_records:
        cluster = None
        for key in ("cluster_id", "cluster", "wallet_cluster", "wallet_cluster_id"):
            cluster = record.get(key)
            if cluster not in (None, ""):
                break
        cluster_values.append(_normalize_bucket(cluster, "cluster"))
    if any(cluster_values):
        dimensions.append([value for value in cluster_values if value])

    if not any(dimensions):
        return None

    def _normalized_entropy(values: list[str]) -> float:
        counts: dict[str, int] = defaultdict(int)
        for value in values:
            counts[value] += 1
        total = sum(counts.values())
        if total <= 1 or len(counts) <= 1:
            return 0.0
        entropy = -sum((count / total) * log(count / total) for count in counts.values())
        return entropy / log(len(counts))

    dimension_scores = [_normalized_entropy(values) for values in dimensions if values]
    if not dimension_scores:
        return None
    count_factor = min(1.0, max(0.0, (len(matched_records) - 1) / 3.0))
    return round(sum(dimension_scores) / len(dimension_scores) * count_factor, 6)


def _first_visible_author_ts(card: dict[str, Any]) -> int:
    for key in ("created_at", "posted_at", "published_at", "timestamp", "tweet_created_at"):
        ts = _parse_ts(card.get(key))
        if ts > 0:
            return ts
    return 0


def compute_x_author_velocity_5m(snapshots: list[dict[str, Any]]) -> float | None:
    first_seen: dict[str, int] = {}
    for snapshot in snapshots:
        cards = snapshot.get("cards") if isinstance(snapshot.get("cards"), list) else []
        for card in cards:
            if not isinstance(card, dict):
                continue
            author = _normalize_wallet(card.get("author_handle") or card.get("author") or card.get("handle"))
            ts = _first_visible_author_ts(card)
            if not author or ts <= 0:
                continue
            first_seen[author] = min(first_seen.get(author, ts), ts)

    if not first_seen:
        return None

    start_ts = min(first_seen.values())
    authors_in_window = sum(1 for ts in first_seen.values() if ts <= start_ts + _X_WINDOW_5M)
    return round(authors_in_window / 5.0, 6)


def compute_seller_reentry_ratio(*, pair_created_ts: int, txs: list[dict[str, Any]], window_sec: int = _SHORT_WINDOW_120S) -> float | None:
    lifecycle: dict[str, list[tuple[int, str]]] = defaultdict(list)
    saw_transfer = False
    for tx in _window_transactions(txs, pair_created_ts, window_sec):
        ts = int(tx.get("_parsed_ts") or 0)
        for transfer in _iter_token_transfers(tx):
            amount = _transfer_amount(transfer)
            if amount is None:
                continue
            buyer = _normalize_wallet(transfer.get("toUserAccount") or transfer.get("toUser") or transfer.get("buyer"))
            seller = _normalize_wallet(transfer.get("fromUserAccount") or transfer.get("fromUser") or transfer.get("seller"))
            if buyer:
                lifecycle[buyer].append((ts, "buy"))
                saw_transfer = True
            if seller:
                lifecycle[seller].append((ts, "sell"))
                saw_transfer = True

    if not saw_transfer:
        return None

    seller_population = 0
    seller_reentries = 0
    for wallet, events in lifecycle.items():
        ordered = sorted(events)
        first_sell_idx = next((idx for idx, (_, side) in enumerate(ordered) if side == "sell"), None)
        if first_sell_idx is None:
            continue
        if not any(side == "buy" for _, side in ordered[:first_sell_idx]):
            continue
        seller_population += 1
        if any(side == "buy" for _, side in ordered[first_sell_idx + 1 :]):
            seller_reentries += 1

    if seller_population == 0:
        return None
    return round(seller_reentries / seller_population, 6)


def compute_liquidity_shock_recovery_sec(*, pair_created_ts: int, txs: list[dict[str, Any]]) -> int | None:
    points = _liquidity_points_120s(pair_created_ts=pair_created_ts, txs=txs)
    if len(points) < 2:
        return None

    baseline_ts, baseline = points[0]
    if baseline <= 0:
        return None

    shock_point = min(points[1:], key=lambda item: (item[1], item[0]), default=points[0])
    shock_ts, shock_value = shock_point
    if shock_ts == baseline_ts:
        return None
    shock_drop_ratio = (baseline - shock_value) / baseline if baseline > 0 else 0.0
    if shock_drop_ratio < _MIN_LIQUIDITY_SHOCK_RATIO:
        return None

    for ts, liquidity in points:
        if ts <= shock_ts:
            continue
        if liquidity >= baseline:
            return ts - shock_ts
    return None


__all__ = [
    "compute_cluster_sell_concentration_120s",
    "compute_liquidity_refill_ratio_120s",
    "compute_liquidity_shock_recovery_sec",
    "compute_net_unique_buyers_60s",
    "compute_seller_reentry_ratio",
    "compute_smart_wallet_dispersion_score",
    "compute_x_author_velocity_5m",
]
