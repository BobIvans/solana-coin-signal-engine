"""Thin Solana RPC client wrappers used by on-chain enrichment."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from data.tx_cache_policy import resolve_tx_fetch_mode
from data.tx_lake import load_tx_batch, make_tx_lake_event, write_tx_batch
from data.tx_normalizer import normalize_tx_batch


class SolanaRpcClient:
    def __init__(
        self,
        rpc_url: str,
        commitment: str = "confirmed",
        *,
        tx_lake_dir: str | None = None,
        tx_cache_ttl_sec: int = 900,
        stale_tx_cache_ttl_sec: int = 86_400,
        allow_stale_tx_cache: bool = True,
    ) -> None:
        self.rpc_url = rpc_url
        self.commitment = commitment
        self.tx_lake_dir = tx_lake_dir
        self.tx_cache_ttl_sec = max(int(tx_cache_ttl_sec or 0), 0)
        self.stale_tx_cache_ttl_sec = max(int(stale_tx_cache_ttl_sec or 0), self.tx_cache_ttl_sec)
        self.allow_stale_tx_cache = bool(allow_stale_tx_cache)

    def _rpc(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        req = Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "scse/0.1"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict) or data.get("error"):
            return None
        return data.get("result")

    def get_token_largest_accounts(self, mint: str) -> dict[str, Any]:
        result = self._rpc("getTokenLargestAccounts", [mint, {"commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": []}

    def get_token_supply(self, mint: str) -> dict[str, Any]:
        result = self._rpc("getTokenSupply", [mint, {"commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": {"amount": "0", "decimals": 0, "uiAmount": 0.0}}

    def get_token_accounts_by_owner(self, owner: str, mint: str | None = None) -> dict[str, Any]:
        filt: dict[str, Any] = {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}
        if mint:
            filt = {"mint": mint}
        result = self._rpc(
            "getTokenAccountsByOwner",
            [owner, filt, {"encoding": "jsonParsed", "commitment": self.commitment}],
        )
        return result if isinstance(result, dict) else {"value": []}

    def get_account_info(self, pubkey: str) -> dict[str, Any] | None:
        result = self._rpc("getAccountInfo", [pubkey, {"encoding": "jsonParsed", "commitment": self.commitment}])
        if not isinstance(result, dict):
            return None
        value = result.get("value")
        return value if isinstance(value, dict) else None

    def _finalize_tx_response(
        self,
        tx_batch: dict[str, Any] | None,
        *,
        lookup_key: str,
        tx_fetch_mode: str,
        events: list[dict[str, Any]],
        batch_warning: str | None = None,
    ) -> dict[str, Any]:
        batch = tx_batch if isinstance(tx_batch, dict) else {
            "lookup_key": lookup_key,
            "lookup_type": "address",
            "source_provider": "solana_rpc",
            "tx_batch_status": "missing",
            "tx_records": [],
            "record_count": 0,
            "tx_batch_record_count": 0,
        }
        records = batch.get("tx_records") if isinstance(batch.get("tx_records"), list) else []
        return {
            "records": records,
            "tx_batch_path": batch.get("tx_batch_path"),
            "tx_batch_status": batch.get("tx_batch_status") or batch.get("batch_status") or "missing",
            "tx_batch_warning": batch_warning or batch.get("tx_batch_warning"),
            "tx_batch_freshness": batch.get("tx_batch_freshness") or batch.get("freshness_status"),
            "tx_batch_origin": batch.get("tx_batch_origin"),
            "tx_batch_fetched_at": batch.get("tx_batch_fetched_at") or batch.get("fetched_at"),
            "tx_batch_lookup_key": batch.get("tx_batch_lookup_key") or lookup_key,
            "tx_batch_record_count": int(batch.get("tx_batch_record_count") or batch.get("record_count") or len(records)),
            "tx_fetch_mode": tx_fetch_mode,
            "tx_lake_events": events,
        }

    def get_signatures_for_address_with_status(
        self,
        address: str,
        limit: int = 40,
        *,
        allow_stale: bool | None = None,
        max_age_sec: int | None = None,
    ) -> dict[str, Any]:
        allow_stale = self.allow_stale_tx_cache if allow_stale is None else bool(allow_stale)
        ttl = self.tx_cache_ttl_sec if max_age_sec is None else max(int(max_age_sec), 0)
        lookup_key = str(address or "").strip()
        events = [make_tx_lake_event("tx_lake_lookup_started", lookup_key=lookup_key, lookup_type="address", provider="solana_rpc")]
        cached_batch = load_tx_batch(
            lookup_key=lookup_key,
            lookup_type="address",
            provider="solana_rpc",
            root_dir=self.tx_lake_dir,
        )
        fetch_mode = resolve_tx_fetch_mode(
            cached_batch,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        if fetch_mode == "fresh_cache" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_cache_hit", lookup_key=lookup_key, provider="solana_rpc", mode=fetch_mode))
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, tx_fetch_mode=fetch_mode, events=events)

        result = self._rpc("getSignaturesForAddress", [address, {"limit": limit, "commitment": self.commitment}])
        if isinstance(result, list):
            tx_batch = normalize_tx_batch(
                result,
                source_provider="solana_rpc",
                lookup_key=lookup_key,
                lookup_type="address",
                tx_batch_origin="upstream_fetch",
                tx_batch_freshness="fresh_cache",
            )
            path = write_tx_batch(tx_batch, root_dir=self.tx_lake_dir)
            tx_batch["tx_batch_path"] = str(path)
            events.append(make_tx_lake_event("tx_batch_written", lookup_key=lookup_key, provider="solana_rpc", path=str(path), record_count=tx_batch.get("record_count")))
            return self._finalize_tx_response(tx_batch, lookup_key=lookup_key, tx_fetch_mode="refresh_required", events=events)

        fallback_mode = resolve_tx_fetch_mode(
            cached_batch,
            upstream_failed=True,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        if fallback_mode == "upstream_failed_use_stale" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_stale_fallback_used", lookup_key=lookup_key, provider="solana_rpc"))
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, tx_fetch_mode=fallback_mode, events=events, batch_warning="upstream_failed_use_stale")
        events.append(make_tx_lake_event("tx_lake_missing", lookup_key=lookup_key, provider="solana_rpc"))
        return self._finalize_tx_response(None, lookup_key=lookup_key, tx_fetch_mode="missing", events=events, batch_warning="upstream_fetch_failed_and_no_cached_batch")

    def get_signatures_for_address(self, address: str, limit: int = 40) -> list[dict[str, Any]]:
        return self.get_signatures_for_address_with_status(address, limit).get("records", [])

    def get_multiple_accounts(self, pubkeys: list[str]) -> dict[str, Any]:
        keys = [str(key) for key in pubkeys if str(key).strip()][:100]
        if not keys:
            return {"value": []}
        result = self._rpc("getMultipleAccounts", [keys, {"encoding": "jsonParsed", "commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": []}

    def get_token_account_balance(self, token_account: str) -> dict[str, Any]:
        result = self._rpc("getTokenAccountBalance", [token_account, {"commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": {"amount": "0", "decimals": 0, "uiAmount": 0.0}}

