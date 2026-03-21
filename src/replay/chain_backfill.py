from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.price_history_client import PriceHistoryClient
from collectors.solana_rpc_client import SolanaRpcClient


class RateLimiter:
    def __init__(self, max_rps: float) -> None:
        self.interval = 1.0 / max(max_rps, 0.1)
        self.last = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        wait = self.interval - (now - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()



def _cache_key(prefix: str, payload: dict[str, Any]) -> str:
    return prefix + "_" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]



def _cache_read(cache_dir: Path, key: str) -> Any:
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None



def _cache_write(cache_dir: Path, key: str, value: Any) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(json.dumps(value, sort_keys=True), encoding="utf-8")



def _retry(func: Any, attempts: int = 3, delay: float = 0.2) -> Any:
    err: Exception | None = None
    for i in range(attempts):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            err = exc
            if i == attempts - 1:
                raise
            time.sleep(delay * (2**i))
    if err:
        raise err
    return None



def _iso_to_ts(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None



def fetch_signatures_for_address(client: SolanaRpcClient, address: str, *, limit: int, limiter: RateLimiter) -> list[dict[str, Any]]:
    limiter.acquire()
    return _retry(lambda: client.get_signatures_for_address(address, limit=limit)) or []



def fetch_transactions_for_signatures(client: SolanaRpcClient, signatures: list[str], *, limiter: RateLimiter) -> list[dict[str, Any]]:
    txs: list[dict[str, Any]] = []
    for sig in signatures:
        limiter.acquire()
        result = _retry(lambda: client._rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]))
        if isinstance(result, dict):
            txs.append(result)
    return txs



def fetch_block_times(client: SolanaRpcClient, slots: list[int], *, limiter: RateLimiter) -> dict[int, int]:
    out: dict[int, int] = {}
    for slot in slots:
        limiter.acquire()
        value = _retry(lambda: client._rpc("getBlockTime", [slot]))
        if isinstance(value, int):
            out[int(slot)] = value
    return out



def _candidate_start_ts(cand: dict[str, Any], block_times: dict[int, int]) -> int | None:
    raw = cand.get("pair_created_at_ts") or cand.get("pair_created_ts")
    if raw not in (None, ""):
        try:
            ts = int(raw)
            if ts > 0:
                return ts
        except (TypeError, ValueError):
            pass
    iso_ts = _iso_to_ts(cand.get("pair_created_at"))
    if iso_ts:
        return iso_ts
    if block_times:
        return min(int(ts) for ts in block_times.values() if int(ts) > 0)
    return None



def _build_missing_price_path(token: str, pair_address: str, *, warning: str) -> dict[str, Any]:
    return {
        "token_address": token,
        "pair_address": pair_address,
        "source_provider": "price_history",
        "price_path": [],
        "truncated": False,
        "missing": True,
        "price_path_status": "missing",
        "warning": warning,
    }



def _collect_price_paths(cand: dict[str, Any], block_times: dict[int, int], config: dict[str, Any]) -> list[dict[str, Any]]:
    bcfg = config.get("backfill", {})
    token = str(cand.get("token_address") or "")
    pair_address = str(cand.get("pair_address") or "")
    if not bcfg.get("collect_price_paths", True):
        return []
    start_ts = _candidate_start_ts(cand, block_times)
    if not start_ts:
        return [_build_missing_price_path(token, pair_address, warning="price_path_start_ts_missing")]
    window_sec = max(int(bcfg.get("price_path_window_sec", 900) or 900), 60)
    interval_sec = max(int(bcfg.get("price_interval_sec", 60) or 60), 1)
    client = PriceHistoryClient(
        base_url=bcfg.get("price_history_base_url"),
        api_key=config.get("price_history_api_key"),
        provider=str(bcfg.get("price_provider") or "price_history"),
    )
    path = client.fetch_price_path(
        token_address=token,
        pair_address=pair_address,
        start_ts=start_ts,
        end_ts=start_ts + window_sec,
        interval_sec=interval_sec,
        limit=max(int(bcfg.get("price_path_limit", 256) or 256), 1),
    )
    return [path]



def build_chain_context(candidates: list[dict[str, Any]], config: dict[str, Any], *, dry_run: bool) -> list[dict[str, Any]]:
    bcfg = config.get("backfill", {})
    if dry_run:
        rows = []
        for row in candidates:
            i = int(str(row.get("token_address", "0")).split("_")[-1] or 0)
            start_ts = 1_700_000_000 + i * 60
            rows.append(
                {
                    "token_address": row["token_address"],
                    "pair_address": row["pair_address"],
                    "signatures": [f"sig_{i}_{j}" for j in range(3)],
                    "transactions": [{"slot": 1_000_000 + i * 10 + j, "meta": {"fee": 5_000 + j}} for j in range(3)],
                    "block_times": {str(1_000_000 + i * 10 + j): start_ts + j for j in range(3)},
                    "buyer_snapshot": {"buyers_5m": 10 + i, "holders": 100 + i * 2},
                    "price_paths": [{
                        "token_address": row["token_address"],
                        "pair_address": row["pair_address"],
                        "source_provider": "dry_run",
                        "price_path": [
                            {"timestamp": start_ts + j * 60, "offset_sec": j * 60, "price": round(1.0 + j * 0.02, 4)}
                            for j in range(6)
                        ],
                        "truncated": False,
                        "missing": False,
                        "price_path_status": "complete",
                        "warning": None,
                    }],
                }
            )
        return rows

    rpc_url = "https://api.mainnet-beta.solana.com"
    if str(bcfg.get("provider", "")).startswith("helius"):
        key = str(config.get("helius_api_key", "")).strip()
        if key:
            rpc_url = f"https://mainnet.helius-rpc.com/?api-key={key}"
    client = SolanaRpcClient(rpc_url=rpc_url)
    limiter = RateLimiter(float(bcfg.get("max_rps", 5)))
    cache_dir = Path(".cache/replay")

    rows: list[dict[str, Any]] = []
    for cand in candidates:
        token = str(cand.get("token_address", ""))
        key = _cache_key(
            "backfill",
            {
                "token": token,
                "limit": int(bcfg.get("max_signatures_per_address", 200)),
                "price_window_sec": int(bcfg.get("price_path_window_sec", 900) or 900),
                "price_interval_sec": int(bcfg.get("price_interval_sec", 60) or 60),
            },
        )
        cached = _cache_read(cache_dir, key) if bcfg.get("cache_enabled", True) else None
        if cached is not None:
            rows.append(cached)
            continue
        signatures_raw = fetch_signatures_for_address(client, token, limit=int(bcfg.get("max_signatures_per_address", 200)), limiter=limiter)
        signatures = [str(item.get("signature", "")) for item in signatures_raw if isinstance(item, dict) and item.get("signature")]
        txs = fetch_transactions_for_signatures(client, signatures[:25], limiter=limiter)
        slots = [int(tx.get("slot", 0) or 0) for tx in txs if int(tx.get("slot", 0) or 0) > 0]
        block_times = fetch_block_times(client, slots, limiter=limiter)
        price_paths = _collect_price_paths(cand, block_times, config)
        row = {
            "token_address": token,
            "pair_address": cand.get("pair_address", ""),
            "signatures": signatures,
            "transactions": txs,
            "block_times": block_times,
            "buyer_snapshot": {"buyers_5m": len(signatures[:20]), "holders": len(signatures[:100])},
            "price_paths": price_paths,
        }
        if bcfg.get("cache_enabled", True):
            _cache_write(cache_dir, key, row)
        rows.append(row)
    return rows
