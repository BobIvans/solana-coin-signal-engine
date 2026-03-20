"""Smoke runner for PR-4 on-chain enrichment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.continuation_enricher import compute_continuation_metrics
from analytics.dev_activity import compute_dev_sell_pressure_5m, infer_dev_wallet
from analytics.holder_metrics import compute_holder_metrics
from analytics.launch_path import estimate_launch_path
from analytics.short_horizon_signals import _parse_ts
from analytics.smart_wallet_hits import compute_smart_wallet_hits
from analytics.wallet_registry_bias import compute_wallet_registry_bias
from collectors.helius_client import HeliusClient
from collectors.solana_rpc_client import SolanaRpcClient
from collectors.wallet_registry_loader import (
    WALLET_REGISTRY_STATUS_EMPTY,
    WALLET_REGISTRY_STATUS_MISSING,
    load_wallet_registry_lookup,
)
from config.settings import load_settings
from utils.bundle_contract_fields import copy_bundle_contract_fields
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json, write_json

CONTRACT_VERSION = "onchain_enrichment_v1"
DEFAULT_VALIDATED_REGISTRY_PATH = Path("data/registry/smart_wallets.validated.json")
DEFAULT_HOT_REGISTRY_PATH = Path("data/registry/hot_wallets.validated.json")


def _null_tx_fetch_payload(*, tx_lookup_source: str | None = None) -> dict:
    return {
        "records": [],
        "tx_batch_status": None,
        "tx_batch_warning": None,
        "tx_batch_freshness": None,
        "tx_batch_origin": None,
        "tx_batch_record_count": None,
        "tx_fetch_mode": None,
        "tx_lake_events": [],
        "tx_lookup_source": tx_lookup_source,
    }


def _tx_warning_reasons(tx_fetch: dict) -> list[str]:
    reasons: list[str] = []
    fetch_mode = str(tx_fetch.get("tx_fetch_mode") or "").strip()
    batch_status = str(tx_fetch.get("tx_batch_status") or "").strip()
    freshness = str(tx_fetch.get("tx_batch_freshness") or "").strip()
    batch_warning = str(tx_fetch.get("tx_batch_warning") or "").strip()

    if batch_warning:
        reasons.append(batch_warning)
    if fetch_mode in {"stale_cache_allowed", "upstream_failed_use_stale", "missing"}:
        reasons.append(fetch_mode)
    if batch_status in {"partial", "malformed", "missing"}:
        reasons.append(f"tx batch {batch_status}")
    if freshness in {"stale_cache_allowed", "unknown", "missing"}:
        reasons.append(f"tx batch freshness {freshness}")
    return sorted(set(reasons))


def _tx_fetch_is_degraded(tx_fetch: dict) -> bool:
    return bool(_tx_warning_reasons(tx_fetch))


def _fetch_token_transactions_with_status(
    helius: HeliusClient,
    rpc: SolanaRpcClient,
    source_addr: str,
    settings,
) -> dict:
    address_fetch = helius.get_transactions_by_address_with_status(source_addr, settings.HELIUS_TX_ADDR_LIMIT)
    address_events = list(address_fetch.get("tx_lake_events") or [])
    if address_fetch.get("records"):
        return {**address_fetch, "tx_lake_events": address_events, "tx_lookup_source": "address"}

    signature_lookup = rpc.get_signatures_for_address_with_status(source_addr, settings.HELIUS_TX_SIG_BATCH)
    signature_events = address_events + list(signature_lookup.get("tx_lake_events") or [])
    signatures = [str(item.get("signature") or "") for item in signature_lookup.get("records", []) if item.get("signature")]
    if not signatures:
        if signature_lookup.get("tx_fetch_mode") == "missing" or signature_lookup.get("tx_batch_status") == "missing":
            warning_parts = [
                str(address_fetch.get("tx_batch_warning") or "").strip(),
                str(signature_lookup.get("tx_batch_warning") or "").strip(),
            ]
            missing_payload = {
                **signature_lookup,
                "tx_lake_events": signature_events,
                "tx_lookup_source": "rpc_signatures_missing",
                "tx_batch_warning": "; ".join(part for part in warning_parts if part) or None,
            }
            return missing_payload
        return {**address_fetch, "tx_lake_events": signature_events, "tx_lookup_source": "address"}

    signature_tx_fetch = helius.get_transactions_by_signatures_with_status(signatures)
    return {
        **signature_tx_fetch,
        "tx_lake_events": signature_events + list(signature_tx_fetch.get("tx_lake_events") or []),
        "tx_lookup_source": "signature_batch",
    }


def _validate_record(record: dict) -> None:
    required = {
        "token_address",
        "top1_holder_share",
        "top20_holder_share",
        "first50_holder_conc_est",
        "holder_entropy_est",
        "unique_buyers_5m",
        "holder_growth_5m",
        "dev_sell_pressure_5m",
        "pumpfun_to_raydium_sec",
        "smart_wallet_hits",
        "wallet_registry_status",
        "wallet_registry_hot_set_size",
        "wallet_registry_validated_size",
        "smart_wallet_score_sum",
        "smart_wallet_tier1_hits",
        "smart_wallet_tier2_hits",
        "smart_wallet_tier3_hits",
        "smart_wallet_early_entry_hits",
        "smart_wallet_active_hits",
        "smart_wallet_watch_hits",
        "smart_wallet_hit_wallets",
        "smart_wallet_hit_tiers",
        "smart_wallet_hit_statuses",
        "smart_wallet_netflow_bias",
        "smart_wallet_conviction_bonus",
        "smart_wallet_registry_confidence",
        "enrichment_status",
        "enrichment_warnings",
        "net_unique_buyers_60s",
        "liquidity_refill_ratio_120s",
        "cluster_sell_concentration_120s",
        "smart_wallet_dispersion_score",
        "x_author_velocity_5m",
        "seller_reentry_ratio",
        "liquidity_shock_recovery_sec",
        "continuation_status",
        "continuation_warning",
        "continuation_confidence",
        "continuation_metric_origin",
        "continuation_coverage_ratio",
        "continuation_inputs_status",
        "continuation_warnings",
        "tx_batch_status",
        "tx_batch_warning",
        "tx_batch_freshness",
        "tx_batch_origin",
        "tx_fetch_mode",
        "tx_batch_record_count",
        "tx_lookup_source",
        "contract_version",
    }
    missing = sorted(required - set(record.keys()))
    if missing:
        raise ValueError(f"enriched schema violation: missing keys {missing}")


def _load_tokens(shortlist_path: Path, x_validated_path: Path) -> list[dict]:
    shortlist_payload = read_json(shortlist_path, default={}) or {}
    x_payload = read_json(x_validated_path, default={}) or {}

    shortlist = shortlist_payload.get("shortlist", []) if isinstance(shortlist_payload, dict) else []
    x_tokens = x_payload.get("tokens", []) if isinstance(x_payload, dict) else []
    x_map = {str(item.get("token_address") or ""): item for item in x_tokens if isinstance(item, dict)}

    merged: list[dict] = []
    for item in shortlist:
        if not isinstance(item, dict):
            continue
        token_address = str(item.get("token_address") or "")
        if not token_address:
            continue
        merged.append({**item, **x_map.get(token_address, {})})
    return merged


def _extract_decimals_from_asset(asset: dict) -> int:
    token_info = asset.get("token_info", {}) if isinstance(asset.get("token_info"), dict) else {}
    return int(token_info.get("decimals") or asset.get("decimals") or 0)


def _default_registry_paths(
    validated_registry_path: Path | None,
    hot_registry_path: Path | None,
) -> tuple[Path, Path]:
    return (
        validated_registry_path or DEFAULT_VALIDATED_REGISTRY_PATH,
        hot_registry_path or DEFAULT_HOT_REGISTRY_PATH,
    )


def run(
    shortlist_path: Path,
    x_validated_path: Path,
    token_override: str | None = None,
    validated_registry_path: Path | None = None,
    hot_registry_path: Path | None = None,
) -> dict:
    settings = load_settings()
    events_path = settings.PROCESSED_DATA_DIR / "onchain_enrichment_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "enrichment_started"})

    validated_registry_path, hot_registry_path = _default_registry_paths(validated_registry_path, hot_registry_path)
    wallet_lookup = load_wallet_registry_lookup(validated_registry_path, hot_registry_path)
    registry_status = str(wallet_lookup.get("status") or WALLET_REGISTRY_STATUS_MISSING)
    registry_event = {
        "ts": utc_now_iso(),
        "wallet_registry_status": registry_status,
        "hot_set_size": int(wallet_lookup.get("hot_set_size") or 0),
        "validated_size": int(wallet_lookup.get("validated_size") or 0),
    }
    if registry_status == WALLET_REGISTRY_STATUS_MISSING:
        append_jsonl(events_path, {**registry_event, "event": "wallet_registry_missing_degraded"})
    elif registry_status == WALLET_REGISTRY_STATUS_EMPTY:
        append_jsonl(events_path, {**registry_event, "event": "wallet_registry_empty_degraded"})
    else:
        append_jsonl(events_path, {**registry_event, "event": "wallet_registry_loaded"})

    tokens = _load_tokens(shortlist_path, x_validated_path)
    if token_override:
        tokens = [token for token in tokens if str(token.get("token_address") or "") == token_override]
    tokens = tokens[: settings.ONCHAIN_ENRICHMENT_MAX_TOKENS]

    rpc = SolanaRpcClient(settings.SOLANA_RPC_URL, settings.SOLANA_RPC_COMMITMENT)
    helius = HeliusClient(settings.HELIUS_API_KEY) if settings.HELIUS_API_KEY else None
    seed_wallets = read_json(settings.SMART_WALLET_SEED_PATH, default=[])
    seed_wallets = seed_wallets if isinstance(seed_wallets, list) else []

    out_tokens: list[dict] = []
    for token in tokens:
        token_address = str(token.get("token_address") or "")
        pair_address = str(token.get("pair_address") or "")
        warnings: list[str] = []
        status = "ok"

        largest = rpc.get_token_largest_accounts(token_address)
        supply = rpc.get_token_supply(token_address)
        holder = compute_holder_metrics(token_address, supply, largest)
        warnings.extend(holder.pop("holder_metrics_warnings"))
        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": "holder_metrics_computed",
                "token_address": token_address,
                "top20_holder_share": holder["top20_holder_share"],
                "warning": "first50_holder_conc_est is heuristic",
            },
        )

        asset: dict = {}
        tx_fetch = _null_tx_fetch_payload(tx_lookup_source="helius_disabled")
        txs: list[dict] = []
        if helius:
            asset = helius.get_asset(token_address)
            if asset:
                append_jsonl(events_path, {"ts": utc_now_iso(), "event": "asset_fetch_succeeded", "token_address": token_address})
            else:
                status = "partial"
                warnings.append("asset metadata missing")
            source_addr = pair_address or token_address
            tx_fetch = _fetch_token_transactions_with_status(helius, rpc, source_addr, settings)
            txs = list(tx_fetch.get("records") or [])
            append_jsonl(
                events_path,
                {
                    "ts": utc_now_iso(),
                    "event": "tx_batch_resolved",
                    "token_address": token_address,
                    "tx_batch_status": tx_fetch.get("tx_batch_status"),
                    "tx_batch_warning": tx_fetch.get("tx_batch_warning"),
                    "tx_batch_freshness": tx_fetch.get("tx_batch_freshness"),
                    "tx_batch_origin": tx_fetch.get("tx_batch_origin"),
                    "tx_fetch_mode": tx_fetch.get("tx_fetch_mode"),
                    "tx_batch_record_count": tx_fetch.get("tx_batch_record_count"),
                    "tx_lookup_source": tx_fetch.get("tx_lookup_source"),
                },
            )
            if _tx_fetch_is_degraded(tx_fetch):
                status = "partial" if status == "ok" else status
                warnings.extend(_tx_warning_reasons(tx_fetch))
        else:
            status = "partial"
            warnings.append("helius disabled: tx-derived metrics may be incomplete")

        token_ctx = {
            "token_address": token_address,
            "pair_address": pair_address,
            "pair_created_at": token.get("pair_created_at"),
            "creator_wallet": token.get("creator_wallet"),
            "mint_authority": token.get("mint_authority"),
            "symbol": token.get("symbol"),
            "name": token.get("name"),
            "x_status": token.get("x_status"),
            "x_snapshots": token.get("x_snapshots") or token.get("x_snapshot_payloads") or token.get("x_snapshot_history"),
            "cards": token.get("cards"),
        }
        dev_wallet = infer_dev_wallet(token_ctx, txs)
        dev_metrics = compute_dev_sell_pressure_5m(dev_wallet.get("dev_wallet_est", ""), token_ctx, txs)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "dev_activity_computed", "token_address": token_address})
        launch = estimate_launch_path(token_ctx, txs)
        append_jsonl(
            events_path,
            {"ts": utc_now_iso(), "event": "launch_path_estimated", "token_address": token_address, "launch_path_label": launch["launch_path_label"]},
        )

        smart_ctx = {
            **token_ctx,
            "smart_wallet_hit_window_sec": settings.SMART_WALLET_HIT_WINDOW_SEC,
            "helius_tx_addr_limit": settings.HELIUS_TX_ADDR_LIMIT,
            "rpc_get_token_accounts_by_owner": rpc.get_token_accounts_by_owner,
            "helius_get_transactions_by_address": helius.get_transactions_by_address if helius else None,
        }
        smart = compute_smart_wallet_hits(token_address, seed_wallets, smart_ctx)
        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": "smart_wallet_hits_computed",
                "token_address": token_address,
                "smart_wallet_hits": smart["smart_wallet_hits"],
            },
        )
        wallet_bias = compute_wallet_registry_bias(smart.get("smart_wallet_hit_wallets") or [], wallet_lookup)
        continuation = compute_continuation_metrics(
            token_ctx=token_ctx,
            txs=txs,
            wallet_lookup=wallet_lookup,
            hit_wallets=smart.get("smart_wallet_hit_wallets") or [],
            pair_created_ts=_parse_ts(token.get("pair_created_at")),
            creator_wallet=str(token.get("creator_wallet") or "") or None,
        )
        for event in continuation.pop("continuation_events", []):
            append_jsonl(events_path, event)

        append_jsonl(
            events_path,
            {
                "ts": utc_now_iso(),
                "event": "token_wallet_hits_computed",
                "token_address": token_address,
                "wallet_registry_status": wallet_bias["wallet_registry_status"],
                "hot_set_size": wallet_bias["wallet_registry_hot_set_size"],
                "validated_size": wallet_bias["wallet_registry_validated_size"],
                "smart_wallet_score_sum": wallet_bias["smart_wallet_score_sum"],
            },
        )

        if wallet_bias["wallet_registry_status"] != "validated":
            warnings.append(f"wallet registry {wallet_bias['wallet_registry_status']}")
        if launch["launch_path_label"] == "unknown":
            warnings.append("launch path unknown")
        if settings.ALLOW_LAUNCH_PATH_HEURISTICS_ONLY:
            status = "partial" if status == "ok" else status
        if continuation["continuation_status"] in {"partial", "missing"}:
            status = "partial" if status == "ok" else status
            if continuation["continuation_warning"]:
                warnings.append(continuation["continuation_warning"])
        warnings.extend(continuation.get("continuation_warnings") or [])

        enriched = {
            "token_address": token_address,
            "symbol": str(token.get("symbol") or ""),
            "name": str(token.get("name") or ""),
            **copy_bundle_contract_fields(token),
            "asset_metadata_present": bool(asset),
            **holder,
            "decimals": _extract_decimals_from_asset(asset) or holder.get("decimals", 0),
            **dev_wallet,
            **dev_metrics,
            **launch,
            **smart,
            **wallet_bias,
            **continuation,
            "tx_batch_status": tx_fetch.get("tx_batch_status"),
            "tx_batch_warning": tx_fetch.get("tx_batch_warning"),
            "tx_batch_freshness": tx_fetch.get("tx_batch_freshness"),
            "tx_batch_origin": tx_fetch.get("tx_batch_origin"),
            "tx_fetch_mode": tx_fetch.get("tx_fetch_mode"),
            "tx_batch_record_count": tx_fetch.get("tx_batch_record_count"),
            "tx_lookup_source": tx_fetch.get("tx_lookup_source"),
            "enrichment_status": status,
            "enrichment_warnings": sorted(set(warnings)),
            "enriched_at": utc_now_iso(),
            "contract_version": CONTRACT_VERSION,
        }
        _validate_record(enriched)
        if status == "partial":
            append_jsonl(
                events_path,
                {"ts": utc_now_iso(), "event": "enrichment_partial", "token_address": token_address, "warnings": enriched["enrichment_warnings"]},
            )
        append_jsonl(
            events_path,
            {"ts": utc_now_iso(), "event": "enrichment_completed", "token_address": token_address, "enrichment_status": status},
        )
        out_tokens.append(enriched)

    payload = {"contract_version": CONTRACT_VERSION, "generated_at": utc_now_iso(), "tokens": out_tokens}
    write_json(settings.PROCESSED_DATA_DIR / "enriched_tokens.json", payload)
    write_json(settings.PROCESSED_DATA_DIR / "enriched_tokens.smoke.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", default="data/processed/shortlist.json")
    parser.add_argument("--x-validated", default="data/processed/x_validated.json")
    parser.add_argument("--validated-registry", default=str(DEFAULT_VALIDATED_REGISTRY_PATH))
    parser.add_argument("--hot-registry", default=str(DEFAULT_HOT_REGISTRY_PATH))
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    payload = run(
        Path(args.shortlist),
        Path(args.x_validated),
        token_override=args.token,
        validated_registry_path=Path(args.validated_registry),
        hot_registry_path=Path(args.hot_registry),
    )
    print(json.dumps(payload.get("tokens", [{}])[0] if payload.get("tokens") else {}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
