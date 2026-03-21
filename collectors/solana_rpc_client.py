"""Thin Solana RPC client wrappers used by on-chain enrichment."""

from __future__ import annotations

import json
from typing import Any

import requests

from data.tx_cache_policy import resolve_tx_fetch_mode
from data.tx_lake import load_tx_batch, make_tx_lake_event, write_tx_batch
from data.tx_normalizer import normalize_tx_batch


TOKEN_PROGRAM_LEGACY = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_PROGRAM_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


_DEFAULT_HEADERS = {"Accept": "application/json", "User-Agent": "scse/0.1"}


def _build_session(session: Any | None = None) -> Any:
    if session is not None:
        return session
    created = requests.Session()
    created.headers.update(_DEFAULT_HEADERS)
    return created


def _session_request(session: Any, method: str, url: str, **kwargs: Any) -> Any:
    request_fn = getattr(session, "request", None)
    if callable(request_fn):
        return request_fn(method, url, **kwargs)
    method_fn = getattr(session, method.lower(), None)
    if callable(method_fn):
        return method_fn(url, **kwargs)
    raise AttributeError(f"session object does not support {method} requests")


def _decode_response_json(response: Any) -> Any:
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return None
    try:
        json_method = getattr(response, "json", None)
        if callable(json_method):
            return json_method()
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _iter_extension_candidates(payload: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for value in (
        payload.get("extensions"),
        (payload.get("data") or {}).get("parsed", {}).get("info", {}).get("extensions") if isinstance(payload.get("data"), dict) else None,
        payload.get("token_info", {}).get("extensions") if isinstance(payload.get("token_info"), dict) else None,
    ):
        if isinstance(value, list):
            candidates.extend(value)
        elif value not in (None, ""):
            candidates.append(value)
    return candidates


def _extension_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        for key in ("extension", "type", "name"):
            raw = value.get(key)
            if raw not in (None, ""):
                return str(raw).strip().lower()
    return ""


def _find_transfer_fee_bps(value: Any) -> float | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in {"transferfeebasispoints", "feebasispoints", "basispoints", "bps", "transfer_fee_bps"}:
                try:
                    return float(nested)
                except (TypeError, ValueError):
                    continue
            found = _find_transfer_fee_bps(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_transfer_fee_bps(item)
            if found is not None:
                return found
    return None


def summarize_token_program_safety(
    account_info: dict[str, Any] | None,
    *,
    transfer_fee_sellability_block_bps: float = 300.0,
) -> dict[str, Any]:
    payload = account_info if isinstance(account_info, dict) else {}
    owner = str(payload.get("owner") or "").strip()
    program_family = "classic_spl" if owner == TOKEN_PROGRAM_LEGACY else ("token_2022" if owner == TOKEN_PROGRAM_2022 else "unknown")
    token_2022_flag = program_family == "token_2022"

    transfer_fee_detected = False
    transfer_fee_bps = 0.0
    extensions = _iter_extension_candidates(payload)
    for extension in extensions:
        name = _extension_name(extension)
        if "transferfee" in name or "transfer_fee" in name:
            transfer_fee_detected = True
            found_bps = _find_transfer_fee_bps(extension)
            if found_bps is not None:
                transfer_fee_bps = max(transfer_fee_bps, found_bps)
    if not transfer_fee_detected:
        found_bps = _find_transfer_fee_bps(payload)
        if found_bps is not None and found_bps > 0:
            transfer_fee_detected = True
            transfer_fee_bps = max(transfer_fee_bps, found_bps)

    if transfer_fee_detected and token_2022_flag:
        warning = "token_2022_transfer_fee_detected"
    elif transfer_fee_detected:
        warning = "transfer_fee_detected"
    elif token_2022_flag and extensions:
        warning = "token_2022_extensions_present"
    elif token_2022_flag:
        warning = "token_2022_program_detected"
    else:
        warning = ""

    sellability_risk_flag = bool(transfer_fee_detected and transfer_fee_bps >= float(transfer_fee_sellability_block_bps or 0.0))
    return {
        "token_program_family": program_family,
        "token_2022_flag": token_2022_flag,
        "transfer_fee_detected": transfer_fee_detected,
        "transfer_fee_bps": round(float(transfer_fee_bps), 6),
        "token_extension_warning": warning,
        "sellability_risk_flag": sellability_risk_flag,
    }


class SolanaRpcClient:
    def __init__(
        self,
        rpc_url: str,
        commitment: str = "confirmed",
        *,
        session: Any | None = None,
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
        self.session = session or requests.Session()
        if hasattr(self.session, "headers"):
            self.session.headers.update(
                {
                    "Accept": "application/json",
                    "User-Agent": "scse/0.1",
                    "Content-Type": "application/json",
                }
            )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        timeout: tuple[int, int] = (3, 15),
    ) -> Any:
        try:
            if method.upper() == "POST":
                response = self.session.post(url, json=json_payload, timeout=timeout)
            else:
                response = self.session.get(url, params=params, timeout=timeout)
        except Exception:
            return None

        if getattr(response, "status_code", 0) != 200:
            return None

        try:
            return response.json()
        except Exception:
            return None

    def _rpc(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        data = self._request_json("POST", self.rpc_url, json_payload=payload, timeout=(3, 15))
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
        if mint:
            result = self._rpc(
                "getTokenAccountsByOwner",
                [owner, {"mint": mint}, {"encoding": "jsonParsed", "commitment": self.commitment}],
            )
            return result if isinstance(result, dict) else {"value": []}

        combined: list[dict[str, Any]] = []
        seen_pubkeys: set[str] = set()
        for program_id in (TOKEN_PROGRAM_LEGACY, TOKEN_PROGRAM_2022):
            result = self._rpc(
                "getTokenAccountsByOwner",
                [owner, {"programId": program_id}, {"encoding": "jsonParsed", "commitment": self.commitment}],
            )
            for row in result.get("value", []) if isinstance(result, dict) else []:
                pubkey = str(row.get("pubkey") or "").strip()
                if pubkey and pubkey in seen_pubkeys:
                    continue
                if pubkey:
                    seen_pubkeys.add(pubkey)
                combined.append(row)
        return {"value": combined}

    def get_account_info(self, pubkey: str) -> dict[str, Any] | None:
        result = self._rpc("getAccountInfo", [pubkey, {"encoding": "jsonParsed", "commitment": self.commitment}])
        if not isinstance(result, dict):
            return None
        value = result.get("value")
        return value if isinstance(value, dict) else None

    def get_program_accounts(self, program_id: str, *, filters: list[dict[str, Any]] | None = None, encoding: str = "jsonParsed") -> list[dict[str, Any]]:
        params: list[Any] = [program_id, {"encoding": encoding, "commitment": self.commitment}]
        if filters:
            params[1]["filters"] = filters
        result = self._rpc("getProgramAccounts", params)
        return result if isinstance(result, list) else []

    def get_mint_holder_owners(self, mint: str) -> list[str]:
        rows = self.get_program_accounts(
            TOKEN_PROGRAM_LEGACY,
            filters=[{"dataSize": 165}, {"memcmp": {"offset": 0, "bytes": mint}}],
        )
        rows_2022 = self.get_program_accounts(
            TOKEN_PROGRAM_2022,
            filters=[{"memcmp": {"offset": 0, "bytes": mint}}],
        )
        owners: list[str] = []
        rows.extend(rows_2022)
        for row in rows:
            account = row.get("account") if isinstance(row, dict) else None
            data = account.get("data") if isinstance(account, dict) else None
            parsed = data.get("parsed") if isinstance(data, dict) else None
            info = parsed.get("info") if isinstance(parsed, dict) else None
            owner = str((info or {}).get("owner") or "").strip()
            if owner and owner not in owners:
                owners.append(owner)
        return owners

    def inspect_token_mint_safety(self, mint: str, *, account_info: dict[str, Any] | None = None) -> dict[str, Any]:
        info = account_info if isinstance(account_info, dict) else self.get_account_info(mint)
        return summarize_token_program_safety(info)

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

