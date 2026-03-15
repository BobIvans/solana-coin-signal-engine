"""Fast, cheap pre-score for early DEX discovery candidates."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_volume_mcap_ratio(pair: dict[str, Any]) -> float:
    volume_m5 = float(pair.get("volume_m5", 0.0) or 0.0)
    market_cap = float(pair.get("market_cap", 0.0) or 0.0)
    fdv = float(pair.get("fdv", 0.0) or 0.0)
    if market_cap > 0:
        return volume_m5 / market_cap
    if fdv > 0:
        return volume_m5 / fdv
    return 0.0


def compute_buy_pressure(pair: dict[str, Any]) -> float:
    buys = int(pair.get("txns_m5_buys", 0) or 0)
    sells = int(pair.get("txns_m5_sells", 0) or 0)
    return buys / max(buys + sells, 1)


def compute_volume_velocity_proxy(pair: dict[str, Any]) -> float:
    volume_m5 = float(pair.get("volume_m5", 0.0) or 0.0)
    liquidity = float(pair.get("liquidity_usd", 0.0) or 0.0)
    return volume_m5 / max(liquidity, 1.0)


def age_freshness_norm(age_sec: int) -> float:
    if age_sec <= 120:
        return 1.0
    if age_sec >= 600:
        return 0.0
    return _clamp((600 - age_sec) / 480.0)


def liquidity_quality_norm(liquidity_usd: float) -> float:
    if liquidity_usd < 20_000:
        return 0.0
    if liquidity_usd <= 80_000:
        return _clamp((liquidity_usd - 20_000) / 60_000)
    if liquidity_usd <= 250_000:
        return 1.0
    if liquidity_usd >= 600_000:
        return 0.0
    return _clamp(1.0 - ((liquidity_usd - 250_000) / 350_000))


def _ratio_norm(value: float, cap: float) -> float:
    return _clamp(value / cap)


def compute_fast_prescore(pair: dict[str, Any], now_ts: int) -> dict[str, Any]:
    created_ts = int(pair.get("pair_created_at_ts", 0) or 0)
    age_sec = max(0, now_ts - created_ts) if created_ts > 0 else 0

    volume_mcap_ratio = compute_volume_mcap_ratio(pair)
    buy_pressure = compute_buy_pressure(pair)
    volume_velocity_proxy = compute_volume_velocity_proxy(pair)

    volume_mcap_ratio_norm = _ratio_norm(volume_mcap_ratio, 0.20)
    buy_pressure_norm = _clamp(buy_pressure)
    volume_velocity_proxy_norm = _ratio_norm(volume_velocity_proxy, 1.0)
    liquidity_quality = liquidity_quality_norm(float(pair.get("liquidity_usd", 0.0) or 0.0))
    age_freshness = age_freshness_norm(age_sec)

    boost_penalty = 0
    if bool(pair.get("paid_order_flag", False)):
        boost_penalty = 20
    elif bool(pair.get("boost_flag", False)):
        boost_penalty = 10

    fast_prescore = (
        0.28 * volume_mcap_ratio_norm
        + 0.22 * buy_pressure_norm
        + 0.18 * volume_velocity_proxy_norm
        + 0.18 * liquidity_quality
        + 0.14 * age_freshness
    ) * 100 - boost_penalty

    fast_prescore = round(_clamp(fast_prescore, 0.0, 100.0), 2)

    return {
        "age_sec": age_sec,
        "volume_mcap_ratio": round(volume_mcap_ratio, 6),
        "buy_pressure": round(buy_pressure, 6),
        "volume_velocity_proxy": round(volume_velocity_proxy, 6),
        "age_freshness_norm": round(age_freshness, 6),
        "liquidity_quality_norm": round(liquidity_quality, 6),
        "boost_penalty": boost_penalty,
        "fast_prescore": fast_prescore,
        # future placeholders (keep explicit to avoid schema drift)
        "bundle_cluster_score": None,
        "first30s_buy_ratio": None,
        "priority_fee_avg_first_min": None,
        "x_validation_score": None,
        "smart_wallet_hits": None,
        "rug_score": None,
    }


def fast_priority_bucket(score: float) -> str:
    if score < 45:
        return "low_priority"
    if score < 65:
        return "weak_watchlist"
    if score < 80:
        return "strong_watchlist"
    return "top_candidate"
