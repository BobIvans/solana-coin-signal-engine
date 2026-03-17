from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from collectors.dexscreener_client import fetch_latest_solana_pairs, normalize_pair
from .deterministic import stable_sort_records


def load_candidates_from_dexscreener(*, start_ts: str, end_ts: str, dry_run: bool) -> list[dict[str, Any]]:
    if dry_run:
        base = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        rows: list[dict[str, Any]] = []
        for idx in range(12):
            discovered = (base - timedelta(minutes=idx * 7)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            rows.append(
                {
                    "token_address": f"token_{idx:03d}",
                    "pair_address": f"pair_{idx:03d}",
                    "discovered_at": discovered,
                    "liquidity_usd": 20_000 + idx * 1_250,
                    "fdv": 80_000 + idx * 7_000,
                    "market_cap": 90_000 + idx * 6_000,
                    "txns_m5": 20 + idx,
                    "paid_order_flag": False,
                    "source_snapshot": {"source": "fixture", "idx": idx},
                }
            )
        return rows

    rows: list[dict[str, Any]] = []
    end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
    for raw in fetch_latest_solana_pairs():
        pair = normalize_pair(raw)
        discovered_ts = int(pair.get("pair_created_at_ts", 0) or 0)
        discovered_at = end_dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        if discovered_ts > 0:
            discovered_at = datetime.fromtimestamp(discovered_ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "token_address": pair.get("token_address", ""),
                "pair_address": pair.get("pair_address", ""),
                "discovered_at": discovered_at,
                "liquidity_usd": float(pair.get("liquidity_usd", 0.0) or 0.0),
                "fdv": float(pair.get("fdv", 0.0) or 0.0),
                "market_cap": float(pair.get("market_cap", 0.0) or 0.0),
                "txns_m5": int(pair.get("txns_m5_buys", 0) or 0) + int(pair.get("txns_m5_sells", 0) or 0),
                "paid_order_flag": bool(pair.get("paid_order_flag", False)),
                "source_snapshot": raw,
            }
        )
    return rows


def filter_candidates(candidates: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    dcfg = config.get("discovery", {})
    out = []
    for row in candidates:
        if float(row.get("liquidity_usd", 0.0)) < float(dcfg.get("liquidity_usd_min", 20_000)):
            continue
        if int(row.get("txns_m5", 0)) < int(dcfg.get("txns_m5_min", 20)):
            continue
        if bool(dcfg.get("require_fdv_or_market_cap", True)) and float(row.get("fdv", 0.0)) <= 0 and float(row.get("market_cap", 0.0)) <= 0:
            continue
        if bool(dcfg.get("exclude_paid_orders", True)) and bool(row.get("paid_order_flag", False)):
            continue
        out.append(row)
    return stable_sort_records(out, ("discovered_at", "token_address", "pair_address"))


def build_replay_universe(*, config: dict[str, Any], start_ts: str, end_ts: str, dry_run: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = load_candidates_from_dexscreener(start_ts=start_ts, end_ts=end_ts, dry_run=dry_run)
    filtered = filter_candidates(candidates, config)
    scored = sorted(filtered, key=lambda x: (-int(x.get("txns_m5", 0)), -float(x.get("liquidity_usd", 0.0)), str(x.get("token_address", ""))))
    shortlist = scored[: int(config.get("discovery", {}).get("shortlist_max", 5))]
    return filtered, shortlist
