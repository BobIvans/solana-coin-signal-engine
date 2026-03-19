"""PR-2 discovery pipeline: fetch, normalize, filter, pre-score, shortlist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analytics.fast_prescore import compute_fast_prescore, fast_priority_bucket
from collectors.bundle_detector import compute_advanced_bundle_fields
from collectors.bundle_detector import detect_bundle_metrics_for_pair, safe_null_bundle_metrics
from collectors.dexscreener_client import fetch_latest_solana_pairs, normalize_pair
from config.settings import load_settings
from utils.bundle_contract_fields import copy_bundle_contract_fields
from utils.clock import utc_now_iso, utc_now_ts
from utils.io import append_jsonl, ensure_dir, write_json
from utils.logger import log_warning


def filter_pair(pair: dict[str, Any], now_ts: int) -> tuple[bool, str]:
    if pair.get("chain") != "solana":
        return False, "non_solana_chain"

    created_ts = int(pair.get("pair_created_at_ts", 0) or 0)
    if created_ts <= 0:
        return False, "missing_pair_created_at"

    age_sec = now_ts - created_ts
    if age_sec >= 600:
        return False, "age_too_high"

    if float(pair.get("liquidity_usd", 0.0) or 0.0) < 20_000:
        return False, "low_liquidity"

    if float(pair.get("fdv", 0.0) or 0.0) <= 0 and float(pair.get("market_cap", 0.0) or 0.0) <= 0:
        return False, "missing_fdv_and_market_cap"

    txns_m5_total = int(pair.get("txns_m5_buys", 0) or 0) + int(pair.get("txns_m5_sells", 0) or 0)
    if txns_m5_total < 20:
        return False, "low_txns_m5"

    if bool(pair.get("paid_order_flag", False)):
        return False, "paid_order"

    return True, "ok"


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda row: (
            -float(row.get("fast_prescore", 0.0) or 0.0),
            -float(row.get("volume_m5", 0.0) or 0.0),
            str(row.get("pair_address", "")),
        ),
    )


def build_shortlist(candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    ranked = rank_candidates(candidates)
    shortlist: list[dict[str, Any]] = []
    for row in ranked[:top_k]:
        shortlist.append(
            {
                "token_address": row.get("token_address", ""),
                "pair_address": row.get("pair_address", ""),
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "fast_prescore": row.get("fast_prescore", 0.0),
                "age_sec": row.get("age_sec", 0),
                "liquidity_usd": row.get("liquidity_usd", 0.0),
                "buy_pressure": row.get("buy_pressure", 0.0),
                "volume_mcap_ratio": row.get("volume_mcap_ratio", 0.0),
                "source": row.get("source", "dexscreener"),
                **copy_bundle_contract_fields(row),
            }
        )
    return shortlist


def _persist_raw_artifacts(raw_pairs: list[dict[str, Any]], timestamp_utc: str, raw_path: Path) -> None:
    for raw_pair in raw_pairs:
        normalized = normalize_pair(raw_pair)
        append_jsonl(
            raw_path,
            {
                "timestamp_utc": timestamp_utc,
                "provider": "dexscreener",
                "artifact_type": "pair_raw",
                "token_address": normalized.get("token_address", ""),
                "payload": raw_pair,
            },
        )


def run_discovery_once() -> dict[str, Any]:
    settings = load_settings()
    ensure_dir(settings.RAW_DATA_DIR)
    ensure_dir(settings.PROCESSED_DATA_DIR)
    ensure_dir(settings.SMOKE_DIR)

    now_ts = int(utc_now_ts())
    timestamp_utc = utc_now_iso()

    raw_pairs = fetch_latest_solana_pairs()
    _persist_raw_artifacts(raw_pairs, timestamp_utc, settings.RAW_DATA_DIR / "discovery_raw.jsonl")

    candidates: list[dict[str, Any]] = []
    bundle_status_counts: dict[str, int] = {}
    bundle_origin_counts: dict[str, int] = {}
    bundle_warnings: list[str] = []
    for raw_pair in raw_pairs:
        normalized = normalize_pair(raw_pair)
        accepted, reason = filter_pair(normalized, now_ts)
        if not accepted:
            continue

        bundle_payload = safe_null_bundle_metrics(status="unavailable", warning="bundle enrichment skipped")
        try:
            bundle_input = {**raw_pair, **normalized}
            if isinstance(raw_pair.get("bundle_transactions"), list):
                bundle_input["bundle_transactions"] = raw_pair.get("bundle_transactions")
            bundle_payload = detect_bundle_metrics_for_pair(bundle_input, now_ts, settings)
        except Exception as exc:  # pragma: no cover - defensive fail-open
            log_warning(
                "bundle_enrichment_failed",
                token_address=normalized.get("token_address", ""),
                pair_address=normalized.get("pair_address", ""),
                error=str(exc),
            )
            bundle_payload = safe_null_bundle_metrics(status="failed", warning=str(exc))

        bundle_status = str(bundle_payload.get("bundle_enrichment_status") or "unknown")
        bundle_status_counts[bundle_status] = bundle_status_counts.get(bundle_status, 0) + 1
        bundle_origin = str(bundle_payload.get("bundle_metric_origin") or "missing")
        bundle_origin_counts[bundle_origin] = bundle_origin_counts.get(bundle_origin, 0) + 1
        warning = str(bundle_payload.get("bundle_enrichment_warning") or bundle_payload.get("bundle_evidence_warning") or "").strip()
        if warning:
            bundle_warnings.append(warning)

        metrics = compute_fast_prescore(normalized, now_ts)
        candidate = {
            **normalized,
            **metrics,
            **bundle_payload,
            "filter_reason": reason,
        }
        candidate["fast_priority_bucket"] = fast_priority_bucket(float(candidate["fast_prescore"]))
        candidate.update(compute_advanced_bundle_fields(candidate=candidate, raw_pair=raw_pair))
        candidates.append(candidate)

    ranked = rank_candidates(candidates)
    top_k = settings.X_MAX_TOKENS_PER_CYCLE
    shortlist = build_shortlist(ranked, top_k=top_k)

    candidates_payload = {
        "timestamp_utc": timestamp_utc,
        "candidate_count": len(ranked),
        "candidates": ranked,
    }
    shortlist_payload = {
        "timestamp_utc": timestamp_utc,
        "top_k": top_k,
        "shortlist": shortlist,
    }

    write_json(settings.PROCESSED_DATA_DIR / "discovery_candidates.json", candidates_payload)
    write_json(settings.PROCESSED_DATA_DIR / "shortlist.json", shortlist_payload)

    status = "ok"
    if not raw_pairs:
        status = "degraded"

    status_payload = {
        "status": status,
        "timestamp_utc": timestamp_utc,
        "pairs_fetched": len(raw_pairs),
        "pairs_filtered_in": len(ranked),
        "shortlist_count": len(shortlist),
        "bundle_enrichment": {
            "enabled": bool(settings.BUNDLE_ENRICHMENT_ENABLED),
            "status_counts": bundle_status_counts,
            "origin_counts": bundle_origin_counts,
            "warnings": sorted(set(bundle_warnings)),
        },
    }
    write_json(settings.SMOKE_DIR / "discovery_status.json", status_payload)

    return {
        "status": status_payload,
        "candidates": candidates_payload,
        "shortlist": shortlist_payload,
    }


def main() -> int:
    result = run_discovery_once()
    print(json.dumps(result["status"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
