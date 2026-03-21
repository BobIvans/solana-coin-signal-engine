"""Helius API wrappers for DAS and enhanced transactions."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data.tx_cache_policy import classify_tx_batch_freshness, resolve_tx_fetch_mode
from data.tx_lake import load_tx_batch, make_tx_lake_event, write_tx_batch
from data.tx_normalizer import normalize_tx_batch


class HeliusClient:
    def __init__(
        self,
        api_key: str,
        *,
        tx_lake_dir: str | None = None,
        tx_cache_ttl_sec: int = 900,
        stale_tx_cache_ttl_sec: int = 86_400,
        allow_stale_tx_cache: bool = True,
    ) -> None:
        self.api_key = api_key
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        self.base_url = "https://api.helius.xyz/v0"
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

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        qs = urlencode({**params, "api-key": self.api_key})
        req = Request(f"{self.base_url}/{endpoint}?{qs}", headers={"Accept": "application/json", "User-Agent": "scse/0.1"})
        try:
            with urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

    def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        req = Request(
            f"{self.base_url}/{endpoint}?api-key={self.api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "scse/0.1"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return None

    def get_asset(self, mint: str) -> dict[str, Any]:
        result = self._rpc("getAsset", [mint])
        return result if isinstance(result, dict) else {}

    def _signature_lookup_key(self, signatures: list[str]) -> str:
        ordered = sorted({str(item).strip() for item in signatures if str(item).strip()})
        if not ordered:
            return "empty-signature-batch"
        digest = hashlib.sha1("|".join(ordered).encode("utf-8")).hexdigest()[:12]
        return f"{ordered[0][:12]}__{len(ordered)}__{digest}"

    def _finalize_tx_response(
        self,
        tx_batch: dict[str, Any] | None,
        *,
        lookup_key: str,
        lookup_type: str,
        tx_fetch_mode: str,
        events: list[dict[str, Any]],
        batch_warning: str | None = None,
    ) -> dict[str, Any]:
        batch = tx_batch if isinstance(tx_batch, dict) else {
            "lookup_key": lookup_key,
            "lookup_type": lookup_type,
            "source_provider": "helius",
            "tx_batch_status": "missing",
            "tx_batch_freshness": "missing",
            "tx_records": [],
            "record_count": 0,
            "tx_batch_record_count": 0,
        }
        freshness = classify_tx_batch_freshness(
            batch,
            max_age_sec=self.tx_cache_ttl_sec,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
        )
        records = batch.get("tx_records") if isinstance(batch.get("tx_records"), list) else []
        warning = batch_warning or batch.get("tx_batch_warning")
        return {
            "records": records,
            "tx_batch_path": batch.get("tx_batch_path"),
            "tx_batch_status": batch.get("tx_batch_status") or batch.get("batch_status") or "missing",
            "tx_batch_warning": warning,
            "tx_batch_freshness": batch.get("tx_batch_freshness") or freshness["freshness"],
            "tx_batch_origin": batch.get("tx_batch_origin"),
            "tx_batch_fetched_at": batch.get("tx_batch_fetched_at") or batch.get("fetched_at"),
            "tx_batch_normalized_at": batch.get("tx_batch_normalized_at") or batch.get("normalized_at"),
            "tx_batch_lookup_key": batch.get("tx_batch_lookup_key") or lookup_key,
            "tx_batch_record_count": int(batch.get("tx_batch_record_count") or batch.get("record_count") or len(records)),
            "tx_batch_pages_loaded": int(batch.get("tx_batch_pages_loaded") or 1),
            "tx_fetch_mode": tx_fetch_mode,
            "tx_lake_events": events,
        }

    @staticmethod
    def _last_signature(records: list[dict[str, Any]]) -> str | None:
        for record in reversed(records):
            signature = str(record.get("signature") or record.get("txHash") or record.get("id") or "").strip()
            if signature:
                return signature
        return None

    @staticmethod
    def _min_record_ts(records: list[dict[str, Any]]) -> int | None:
        values = [int(record.get("timestamp") or record.get("blockTime") or 0) for record in records]
        values = [value for value in values if value > 0]
        return min(values) if values else None

    def get_transactions_by_address_with_status(
        self,
        address: str,
        limit: int = 40,
        *,
        allow_stale: bool | None = None,
        max_age_sec: int | None = None,
        fetch_all: bool = False,
        stop_ts: int | None = None,
        max_pages: int = 8,
    ) -> dict[str, Any]:
        allow_stale = self.allow_stale_tx_cache if allow_stale is None else bool(allow_stale)
        ttl = self.tx_cache_ttl_sec if max_age_sec is None else max(int(max_age_sec), 0)
        lookup_key = str(address or "").strip()
        events = [make_tx_lake_event("tx_lake_lookup_started", lookup_key=lookup_key, lookup_type="address", provider="helius")]
        cached_batch = load_tx_batch(
            lookup_key=lookup_key,
            lookup_type="address",
            provider="helius",
            root_dir=self.tx_lake_dir,
        )
        fetch_mode = resolve_tx_fetch_mode(
            cached_batch,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        if fetch_mode == "fresh_cache" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_cache_hit", lookup_key=lookup_key, provider="helius", mode=fetch_mode))
            warning = cached_batch.get("tx_batch_warning")
            if fetch_mode == "stale_cache_allowed":
                warning = "; ".join(item for item in [warning, "stale_tx_cache_allowed"] if item)
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, lookup_type="address", tx_fetch_mode=fetch_mode, events=events, batch_warning=warning)

        events.append(make_tx_lake_event("tx_lake_refresh_started", lookup_key=lookup_key, provider="helius"))
        query = {"limit": limit}
        raw_result = self._get(f"addresses/{lookup_key}/transactions", query)
        if isinstance(raw_result, list):
            combined_records = list(raw_result)
            next_before = self._last_signature(raw_result)
            pages_loaded = 1
            while fetch_all and next_before and len(raw_result) >= limit and pages_loaded < max(max_pages, 1):
                oldest_ts = self._min_record_ts(raw_result)
                if stop_ts and oldest_ts and oldest_ts <= stop_ts:
                    break
                raw_result = self._get(f"addresses/{lookup_key}/transactions", {"limit": limit, "before": next_before})
                if not isinstance(raw_result, list) or not raw_result:
                    break
                combined_records.extend(raw_result)
                next_before = self._last_signature(raw_result)
                pages_loaded += 1
            tx_batch = normalize_tx_batch(
                combined_records,
                source_provider="helius",
                lookup_key=lookup_key,
                lookup_type="address",
                tx_batch_origin="upstream_fetch",
                tx_batch_freshness="fresh_cache",
            )
            path = write_tx_batch(tx_batch, root_dir=self.tx_lake_dir)
            tx_batch["tx_batch_path"] = str(path)
            tx_batch["tx_batch_pages_loaded"] = pages_loaded
            events.append(make_tx_lake_event("tx_batch_normalized", lookup_key=lookup_key, provider="helius", record_count=tx_batch.get("record_count"), batch_status=tx_batch.get("tx_batch_status")))
            events.append(make_tx_lake_event("tx_batch_written", lookup_key=lookup_key, provider="helius", path=str(path), record_count=tx_batch.get("record_count")))
            events.append(make_tx_lake_event("tx_lake_refresh_completed", lookup_key=lookup_key, provider="helius", record_count=tx_batch.get("record_count"), pages_loaded=pages_loaded))
            return self._finalize_tx_response(tx_batch, lookup_key=lookup_key, lookup_type="address", tx_fetch_mode="refresh_required", events=events)

        fallback_mode = resolve_tx_fetch_mode(
            cached_batch,
            upstream_failed=True,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        events.append(make_tx_lake_event("tx_lake_refresh_failed", lookup_key=lookup_key, provider="helius"))
        if fallback_mode == "upstream_failed_use_stale" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_stale_fallback_used", lookup_key=lookup_key, provider="helius"))
            warning = "; ".join(item for item in [cached_batch.get("tx_batch_warning"), "upstream_failed_use_stale"] if item)
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, lookup_type="address", tx_fetch_mode=fallback_mode, events=events, batch_warning=warning)

        events.append(make_tx_lake_event("tx_lake_missing", lookup_key=lookup_key, provider="helius"))
        return self._finalize_tx_response(None, lookup_key=lookup_key, lookup_type="address", tx_fetch_mode="missing", events=events, batch_warning="upstream_fetch_failed_and_no_cached_batch")

    def get_transactions_by_address(self, address: str, limit: int = 40) -> list[dict[str, Any]]:
        return self.get_transactions_by_address_with_status(address, limit).get("records", [])

    def get_transactions_by_signatures_with_status(
        self,
        signatures: list[str],
        *,
        allow_stale: bool | None = None,
        max_age_sec: int | None = None,
    ) -> dict[str, Any]:
        normalized_signatures = [str(signature).strip() for signature in signatures if str(signature).strip()]
        if not normalized_signatures:
            return self._finalize_tx_response(None, lookup_key="empty-signature-batch", lookup_type="signature_batch", tx_fetch_mode="missing", events=[], batch_warning="signature list empty")
        allow_stale = self.allow_stale_tx_cache if allow_stale is None else bool(allow_stale)
        ttl = self.tx_cache_ttl_sec if max_age_sec is None else max(int(max_age_sec), 0)
        lookup_key = self._signature_lookup_key(normalized_signatures)
        events = [make_tx_lake_event("tx_lake_lookup_started", lookup_key=lookup_key, lookup_type="signature_batch", provider="helius")]
        cached_batch = load_tx_batch(
            lookup_key=lookup_key,
            lookup_type="signature_batch",
            provider="helius",
            root_dir=self.tx_lake_dir,
        )
        fetch_mode = resolve_tx_fetch_mode(
            cached_batch,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        if fetch_mode == "fresh_cache" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_cache_hit", lookup_key=lookup_key, provider="helius", mode=fetch_mode))
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, lookup_type="signature_batch", tx_fetch_mode=fetch_mode, events=events)

        raw_result = self._post("transactions", {"transactions": normalized_signatures})
        if isinstance(raw_result, list):
            tx_batch = normalize_tx_batch(
                raw_result,
                source_provider="helius",
                lookup_key=lookup_key,
                lookup_type="signature_batch",
                tx_batch_origin="upstream_fetch",
                tx_batch_freshness="fresh_cache",
            )
            path = write_tx_batch(tx_batch, root_dir=self.tx_lake_dir)
            tx_batch["tx_batch_path"] = str(path)
            events.append(make_tx_lake_event("tx_batch_written", lookup_key=lookup_key, provider="helius", path=str(path), record_count=tx_batch.get("record_count")))
            return self._finalize_tx_response(tx_batch, lookup_key=lookup_key, lookup_type="signature_batch", tx_fetch_mode="refresh_required", events=events)

        fallback_mode = resolve_tx_fetch_mode(
            cached_batch,
            upstream_failed=True,
            max_age_sec=ttl,
            stale_age_sec=self.stale_tx_cache_ttl_sec,
            allow_stale=allow_stale,
        )
        if fallback_mode == "upstream_failed_use_stale" and isinstance(cached_batch, dict):
            events.append(make_tx_lake_event("tx_lake_stale_fallback_used", lookup_key=lookup_key, provider="helius"))
            return self._finalize_tx_response(cached_batch, lookup_key=lookup_key, lookup_type="signature_batch", tx_fetch_mode=fallback_mode, events=events, batch_warning="upstream_failed_use_stale")
        events.append(make_tx_lake_event("tx_lake_missing", lookup_key=lookup_key, provider="helius"))
        return self._finalize_tx_response(None, lookup_key=lookup_key, lookup_type="signature_batch", tx_fetch_mode="missing", events=events, batch_warning="upstream_fetch_failed_and_no_cached_batch")

    def get_transactions_by_signatures(self, signatures: list[str]) -> list[dict[str, Any]]:
        return self.get_transactions_by_signatures_with_status(signatures).get("records", [])
