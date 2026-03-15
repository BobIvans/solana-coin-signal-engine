"""Smoke runner for PR-4 on-chain enrichment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.dev_activity import compute_dev_sell_pressure_5m, infer_dev_wallet
from analytics.holder_metrics import compute_holder_metrics
from analytics.launch_path import estimate_launch_path
from analytics.smart_wallet_hits import compute_smart_wallet_hits
from collectors.helius_client import HeliusClient
from collectors.solana_rpc_client import SolanaRpcClient
from config.settings import load_settings
from utils.clock import utc_now_iso
from utils.io import append_jsonl, read_json, write_json

CONTRACT_VERSION = "onchain_enrichment_v1"


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
        "enrichment_status",
        "enrichment_warnings",
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


def run(shortlist_path: Path, x_validated_path: Path, token_override: str | None = None) -> dict:
    settings = load_settings()
    events_path = settings.PROCESSED_DATA_DIR / "onchain_enrichment_events.jsonl"
    append_jsonl(events_path, {"ts": utc_now_iso(), "event": "enrichment_started"})

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
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "holder_metrics_computed", "token_address": token_address, "top20_holder_share": holder["top20_holder_share"], "warning": "first50_holder_conc_est is heuristic"})

        asset: dict = {}
        txs: list[dict] = []
        if helius:
            asset = helius.get_asset(token_address)
            if asset:
                append_jsonl(events_path, {"ts": utc_now_iso(), "event": "asset_fetch_succeeded", "token_address": token_address})
            else:
                status = "partial"
                warnings.append("asset metadata missing")

            source_addr = pair_address or token_address
            txs = helius.get_transactions_by_address(source_addr, settings.HELIUS_TX_ADDR_LIMIT)
            if not txs:
                sigs = rpc.get_signatures_for_address(source_addr, settings.HELIUS_TX_SIG_BATCH)
                signatures = [str(item.get("signature") or "") for item in sigs if item.get("signature")]
                txs = helius.get_transactions_by_signatures(signatures)
                if signatures and not txs:
                    status = "partial"
                    warnings.append("enhanced transaction batch fetch failed")
        else:
            status = "partial"
            warnings.append("helius disabled: tx-derived metrics may be incomplete")

        token_ctx = {
            "pair_created_at": token.get("pair_created_at"),
            "creator_wallet": token.get("creator_wallet"),
            "mint_authority": token.get("mint_authority"),
        }
        dev_wallet = infer_dev_wallet(token_ctx, txs)
        dev_metrics = compute_dev_sell_pressure_5m(dev_wallet.get("dev_wallet_est", ""), token_ctx, txs)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "dev_activity_computed", "token_address": token_address})

        launch = estimate_launch_path(token_ctx, txs)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "launch_path_estimated", "token_address": token_address, "launch_path_label": launch["launch_path_label"]})

        smart_ctx = {
            **token_ctx,
            "smart_wallet_hit_window_sec": settings.SMART_WALLET_HIT_WINDOW_SEC,
            "helius_tx_addr_limit": settings.HELIUS_TX_ADDR_LIMIT,
            "rpc_get_token_accounts_by_owner": rpc.get_token_accounts_by_owner,
            "helius_get_transactions_by_address": helius.get_transactions_by_address if helius else None,
        }
        smart = compute_smart_wallet_hits(token_address, seed_wallets, smart_ctx)
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "smart_wallet_hits_computed", "token_address": token_address, "smart_wallet_hits": smart["smart_wallet_hits"]})

        if launch["launch_path_label"] == "unknown":
            warnings.append("launch path unknown")
            if settings.ALLOW_LAUNCH_PATH_HEURISTICS_ONLY:
                status = "partial" if status == "ok" else status

        enriched = {
            "token_address": token_address,
            "symbol": str(token.get("symbol") or ""),
            "name": str(token.get("name") or ""),
            "asset_metadata_present": bool(asset),
            **holder,
            "decimals": _extract_decimals_from_asset(asset) or holder.get("decimals", 0),
            **dev_wallet,
            **dev_metrics,
            **launch,
            **smart,
            "enrichment_status": status,
            "enrichment_warnings": sorted(set(warnings)),
            "enriched_at": utc_now_iso(),
            "contract_version": CONTRACT_VERSION,
        }
        _validate_record(enriched)
        if status == "partial":
            append_jsonl(events_path, {"ts": utc_now_iso(), "event": "enrichment_partial", "token_address": token_address, "warnings": enriched["enrichment_warnings"]})
        append_jsonl(events_path, {"ts": utc_now_iso(), "event": "enrichment_completed", "token_address": token_address, "enrichment_status": status})
        out_tokens.append(enriched)

    payload = {"contract_version": CONTRACT_VERSION, "generated_at": utc_now_iso(), "tokens": out_tokens}
    write_json(settings.PROCESSED_DATA_DIR / "enriched_tokens.json", payload)
    write_json(settings.PROCESSED_DATA_DIR / "enriched_tokens.smoke.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", default="data/processed/shortlist.json")
    parser.add_argument("--x-validated", default="data/processed/x_validated.json")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    payload = run(Path(args.shortlist), Path(args.x_validated), token_override=args.token)
    print(json.dumps(payload.get("tokens", [{}])[0] if payload.get("tokens") else {}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
