from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

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


def build_chain_context(candidates: list[dict[str, Any]], config: dict[str, Any], *, dry_run: bool) -> list[dict[str, Any]]:
    bcfg = config.get("backfill", {})
    if dry_run:
        rows = []
        for row in candidates:
            i = int(str(row.get("token_address", "0")).split("_")[-1] or 0)
            rows.append(
                {
                    "token_address": row["token_address"],
                    "pair_address": row["pair_address"],
                    "signatures": [f"sig_{i}_{j}" for j in range(3)],
                    "transactions": [{"slot": 1_000_000 + i * 10 + j, "meta": {"fee": 5_000 + j}} for j in range(3)],
                    "block_times": {str(1_000_000 + i * 10 + j): 1_700_000_000 + i * 60 + j for j in range(3)},
                    "buyer_snapshot": {"buyers_5m": 10 + i, "holders": 100 + i * 2},
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
        key = _cache_key("backfill", {"token": token, "limit": int(bcfg.get("max_signatures_per_address", 200))})
        cached = _cache_read(cache_dir, key) if bcfg.get("cache_enabled", True) else None
        if cached is not None:
            rows.append(cached)
            continue
        signatures_raw = fetch_signatures_for_address(client, token, limit=int(bcfg.get("max_signatures_per_address", 200)), limiter=limiter)
        signatures = [str(item.get("signature", "")) for item in signatures_raw if isinstance(item, dict) and item.get("signature")]
        txs = fetch_transactions_for_signatures(client, signatures[:25], limiter=limiter)
        slots = [int(tx.get("slot", 0) or 0) for tx in txs if int(tx.get("slot", 0) or 0) > 0]
        block_times = fetch_block_times(client, slots, limiter=limiter)
        row = {
            "token_address": token,
            "pair_address": cand.get("pair_address", ""),
            "signatures": signatures,
            "transactions": txs,
            "block_times": block_times,
            "buyer_snapshot": {"buyers_5m": len(signatures[:20]), "holders": len(signatures[:100])},
        }
        if bcfg.get("cache_enabled", True):
            _cache_write(cache_dir, key, row)
        rows.append(row)
    return rows
