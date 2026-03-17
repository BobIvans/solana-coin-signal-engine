from __future__ import annotations

from typing import Any


def inject_degraded_x_fields(signal: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    xcfg = config.get("x_mode", {})
    signal["x_status"] = str(xcfg.get("status", "degraded"))
    signal["x_validation_score"] = int(xcfg.get("baseline_score", 45))
    signal["x_validation_delta"] = float(xcfg.get("baseline_delta", 0))
    return signal


def build_features_for_step(candidate: dict[str, Any], backfill: dict[str, Any], config: dict[str, Any], *, wallet_weighting: bool) -> dict[str, Any]:
    liq = float(candidate.get("liquidity_usd", 0.0) or 0.0)
    fdv = float(candidate.get("fdv", 0.0) or 0.0) + float(candidate.get("market_cap", 0.0) or 0.0) + 1.0
    txns_m5 = float(candidate.get("txns_m5", 0) or 0)
    buyers_5m = float(backfill.get("buyer_snapshot", {}).get("buyers_5m", 0) or 0)
    holders = float(backfill.get("buyer_snapshot", {}).get("holders", 0) or 0)
    sig_count = float(len(backfill.get("signatures", [])))

    smart_hits = int(min(3, sig_count // 20))
    if wallet_weighting:
        smart_hits += 1

    features = {
        "volume_mcap_ratio": round((txns_m5 * 250) / fdv, 6),
        "volume_velocity": round(txns_m5 / 5.0 + sig_count / 50.0, 6),
        "buy_pressure": round(min(0.99, (buyers_5m + 1) / (txns_m5 + 2)), 6),
        "holder_growth_5m": int(buyers_5m),
        "top20_holder_share": round(min(0.95, 20 / max(holders, 21)), 6),
        "rug_score_light": round(max(0.01, min(0.99, 1 - (liq / max(fdv, 1.0)))), 6),
        "smart_wallet_hits": smart_hits,
        "dev_wallet_activity_flag": bool(sig_count > 30),
    }
    return features
