"""DEXScreener discovery client + defensive normalizer for Solana pairs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search/?q=solana"


def _to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _to_iso_and_ts(raw_created_at: Any) -> tuple[str | None, int]:
    if raw_created_at in (None, ""):
        return None, 0

    ts = _to_int(raw_created_at)
    if ts <= 0:
        return None, 0

    # DexScreener often sends milliseconds.
    if ts > 10_000_000_000:
        ts = int(ts / 1000)

    try:
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None, 0

    return iso, ts


def fetch_latest_solana_pairs() -> list[dict[str, Any]]:
    request = Request(DEXSCREENER_SEARCH_URL, headers={"Accept": "application/json", "User-Agent": "scse/0.1"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError):
        return []

    pairs = payload.get("pairs", [])
    if not isinstance(pairs, list):
        return []

    return [pair for pair in pairs if isinstance(pair, dict)]


def extract_pair_metrics(pair: dict[str, Any]) -> dict[str, Any]:
    txns_m5 = pair.get("txns", {}).get("m5", {}) if isinstance(pair.get("txns"), dict) else {}
    volume = pair.get("volume", {}) if isinstance(pair.get("volume"), dict) else {}
    liquidity = pair.get("liquidity", {}) if isinstance(pair.get("liquidity"), dict) else {}

    return {
        "price_usd": _to_float(pair.get("priceUsd")),
        "liquidity_usd": _to_float(liquidity.get("usd")),
        "fdv": _to_float(pair.get("fdv")),
        "market_cap": _to_float(pair.get("marketCap")),
        "volume_m5": _to_float(volume.get("m5")),
        "volume_h1": _to_float(volume.get("h1")),
        "txns_m5_buys": _to_int(txns_m5.get("buys")),
        "txns_m5_sells": _to_int(txns_m5.get("sells")),
    }


def normalize_pair(raw_pair: dict[str, Any]) -> dict[str, Any]:
    base_token = raw_pair.get("baseToken", {}) if isinstance(raw_pair.get("baseToken"), dict) else {}
    token_address = str(base_token.get("address") or "")

    pair_created_at, pair_created_at_ts = _to_iso_and_ts(raw_pair.get("pairCreatedAt"))

    boost = raw_pair.get("boosts", {}) if isinstance(raw_pair.get("boosts"), dict) else {}
    info = raw_pair.get("info", {}) if isinstance(raw_pair.get("info"), dict) else {}

    return {
        "token_address": token_address,
        "pair_address": str(raw_pair.get("pairAddress") or ""),
        "symbol": str(base_token.get("symbol") or ""),
        "name": str(base_token.get("name") or ""),
        "chain": str(raw_pair.get("chainId") or "").lower(),
        "dex_id": str(raw_pair.get("dexId") or ""),
        "pair_created_at": pair_created_at,
        "pair_created_at_ts": pair_created_at_ts,
        **extract_pair_metrics(raw_pair),
        "boost_flag": _to_bool(boost.get("active")) or _to_bool(raw_pair.get("boosted")),
        "paid_order_flag": _to_bool(info.get("paid")) or _to_bool(raw_pair.get("paidOrder")),
        "source": "dexscreener",
    }
