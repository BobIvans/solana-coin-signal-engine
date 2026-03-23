"""Canonical historical price-path collection helpers for replay backfill."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_PROVIDER_ALIASES = {
    "price_history": "price_history",
    "geckoterminal": "geckoterminal_pool_ohlcv",
    "geckoterminal_pool": "geckoterminal_pool_ohlcv",
    "geckoterminal_pool_ohlcv": "geckoterminal_pool_ohlcv",
}

_PROVIDER_DEFAULTS = {
    "price_history": {
        "base_url": None,
        "endpoint": "price-history",
        "request_kind": "price_history",
        "auth_header": None,
        "require_pair_address": False,
        "allow_pairless_token_lookup": False,
    },
    "geckoterminal_pool_ohlcv": {
        "base_url": "https://api.geckoterminal.com/api/v2",
        "token_endpoint": "networks/{network}/tokens/{token_address}/pools",
        "pair_endpoint": "networks/{network}/pools/{pool_address}/ohlcv/{timeframe}",
        "request_kind": "pool_ohlcv",
        "auth_header": None,
        "require_pair_address": False,
        "allow_pairless_token_lookup": True,
        "network": "solana",
        "currency": "usd",
        "token": "base",
        "token_side": "base",
        "include_empty_intervals": True,
        "pool_resolver": "geckoterminal",
        "resolver_cache_ttl_sec": 86400,
        "max_ohlcv_limit": 1000,
        "request_version": "20230302",
    },
}

_SUMMARY_FIELDS = (
    "base_url",
    "request_kind",
    "network",
    "currency",
    "token",
    "token_side",
    "include_empty_intervals",
    "pool_resolver",
    "resolver_cache_ttl_sec",
    "max_ohlcv_limit",
    "request_version",
    "allow_pairless_token_lookup",
    "require_pair_address",
)


def _coerce_int(value: Any) -> int | None:
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None



def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None



def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current



def _normalize_provider_name(provider: str | None) -> str:
    key = str(provider or "price_history").strip().lower()
    return _PROVIDER_ALIASES.get(key, key or "price_history")



def validate_price_history_provider_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(config or {})
    provider = _normalize_provider_name(raw.get("provider"))
    defaults = dict(_PROVIDER_DEFAULTS.get(provider, _PROVIDER_DEFAULTS["price_history"]))
    merged = {**defaults, **{k: v for k, v in raw.items() if v is not None}}
    merged["provider"] = provider
    merged["provider_bootstrap_ok"] = True
    merged["request_version"] = str(merged.get("request_version") or "").strip() or None
    merged["currency"] = str(merged.get("currency") or "usd").strip().lower() or "usd"
    merged["token_side"] = str(merged.get("token_side") or merged.get("token") or "base").strip().lower() or "base"
    merged["token"] = str(merged.get("token") or merged.get("token_side") or "base").strip().lower() or "base"
    merged["network"] = str(merged.get("network") or merged.get("chain") or "solana").strip().lower() or "solana"
    merged["include_empty_intervals"] = bool(
        True if _coerce_bool(merged.get("include_empty_intervals")) is None else _coerce_bool(merged.get("include_empty_intervals"))
    )
    merged["require_pair_address"] = bool(_coerce_bool(merged.get("require_pair_address")) or False)
    pairless = _coerce_bool(merged.get("allow_pairless_token_lookup"))
    merged["allow_pairless_token_lookup"] = True if pairless is None else bool(pairless)
    merged["resolver_cache_ttl_sec"] = max(int(_coerce_int(merged.get("resolver_cache_ttl_sec")) or 86400), 0)
    merged["max_ohlcv_limit"] = min(max(int(_coerce_int(merged.get("max_ohlcv_limit")) or 1000), 1), 1000)
    return merged


class PriceHistoryClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str = "price_history",
        provider_config: dict[str, Any] | None = None,
    ) -> None:
        config = validate_price_history_provider_config({
            **dict(provider_config or {}),
            "base_url": base_url if base_url is not None else dict(provider_config or {}).get("base_url"),
            "api_key": api_key if api_key is not None else dict(provider_config or {}).get("api_key"),
            "provider": provider or dict(provider_config or {}).get("provider") or "price_history",
        })
        self.provider = config["provider"]
        self.provider_config = config
        self.base_url = str(config.get("base_url") or "").strip().rstrip("/")
        self.api_key = str(config.get("api_key") or "").strip()
        self._resolver_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

    def _request_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "scse/0.1"}
        request_version = self.provider_config.get("request_version")
        if request_version:
            headers["Accept"] = f"application/json;version={request_version}"
        auth_header = self.provider_config.get("auth_header")
        if auth_header and self.api_key:
            headers[str(auth_header)] = self.api_key
        return headers

    def _get(self, endpoint: str, params: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.base_url:
            return {"json": {"rows": [], "missing": True, "warning": "price_history_provider_unconfigured"}, "http_status": None}
        query = {key: value for key, value in dict(params).items() if value not in (None, "")}
        if self.api_key and not self.provider_config.get("auth_header"):
            query.setdefault("api_key", self.api_key)
        req = Request(
            f"{self.base_url}/{endpoint}?{urlencode(query)}",
            headers={**self._request_headers(), **dict(headers or {})},
        )
        try:
            with urlopen(req, timeout=20) as response:
                return {"json": json.loads(response.read().decode("utf-8")), "http_status": getattr(response, "status", 200)}
        except HTTPError as exc:
            payload: Any
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                payload = {"message": str(exc)}
            return {"json": payload, "http_status": exc.code}
        except (URLError, TimeoutError, json.JSONDecodeError):
            return {"json": {"rows": [], "missing": True, "warning": "price_history_request_failed"}, "http_status": None}

    def _normalize_observations(self, rows: list[dict[str, Any]], *, start_ts: int | None) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = _coerce_int(row.get("timestamp") or row.get("ts") or row.get("time") or row.get("t"))
            price = _coerce_float(row.get("price") or row.get("close") or row.get("close_price") or row.get("value"))
            if ts is None or price is None:
                continue
            offset = _coerce_int(row.get("offset_sec") or row.get("elapsed_sec"))
            if offset is None and start_ts is not None:
                offset = max(0, ts - start_ts)
            observations.append({
                "timestamp": ts,
                "offset_sec": int(offset or 0),
                "price": price,
            })
        observations.sort(key=lambda item: (item.get("offset_sec", 0), item.get("timestamp", 0)))
        return observations

    def _provider_request_summary(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        summary = {field: self.provider_config.get(field) for field in _SUMMARY_FIELDS if field in self.provider_config}
        summary["provider"] = self.provider
        if extra:
            summary.update(extra)
        return summary

    def _aggregate_for_interval(self, interval_sec: int) -> int:
        if interval_sec <= 60:
            return 1
        if interval_sec <= 300:
            return 5
        return 15

    def _select_canonical_pool(self, pools: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked: list[tuple[tuple[float, float, str], dict[str, Any]]] = []
        for pool in pools:
            if not isinstance(pool, dict):
                continue
            attrs = pool.get("attributes") if isinstance(pool.get("attributes"), dict) else pool
            address = str(attrs.get("address") or pool.get("pool_address") or "").strip()
            if not address:
                continue
            reserve = _coerce_float(attrs.get("reserve_in_usd")) or 0.0
            volume_bucket = attrs.get("volume_usd")
            volume = 0.0
            if isinstance(volume_bucket, dict):
                for key in ("h24", "24h", "m5", "m15", "h1"):
                    value = _coerce_float(volume_bucket.get(key))
                    if value is not None:
                        volume = value
                        break
            elif volume_bucket is not None:
                volume = _coerce_float(volume_bucket) or 0.0
            ranked.append(((-reserve, -volume, address), {
                "pool_address": address,
                "reserve_in_usd": reserve,
                "volume_usd": volume,
                "raw": pool,
            }))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0])
        return ranked[0][1]

    def _resolve_geckoterminal_pool(self, token_address: str, *, network: str = "solana") -> dict[str, Any]:
        cache_key = (network, token_address)
        now = time.time()
        ttl = int(self.provider_config.get("resolver_cache_ttl_sec") or 0)
        cached = self._resolver_cache.get(cache_key)
        if cached and now - cached[0] <= ttl:
            return dict(cached[1])

        endpoint = str(self.provider_config.get("token_endpoint") or "networks/{network}/tokens/{token_address}/pools").format(
            network=network,
            token_address=token_address,
        )
        response = self._get(endpoint, {})
        payload = response.get("json")
        pools = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), list) else []
        canonical = self._select_canonical_pool(pools)
        result = {
            "pool_address": canonical.get("pool_address") if canonical else None,
            "resolver_source": str(self.provider_config.get("pool_resolver") or "geckoterminal"),
            "resolver_confidence": "high" if canonical else "none",
            "pool_candidates_seen": len(pools),
            "pool_resolution_status": "resolved" if canonical else "pool_resolution_failed",
            "http_status": response.get("http_status"),
        }
        self._resolver_cache[cache_key] = (now, dict(result))
        return result

    def _normalize_geckoterminal_ohlcv_list(
        self,
        rows: list[Any],
        *,
        start_ts: int | None,
        end_ts: int | None,
    ) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            ts = _coerce_int(row[0])
            close = _coerce_float(row[4])
            volume = _coerce_float(row[5])
            if ts is None or close is None:
                continue
            if start_ts is not None and ts < start_ts:
                continue
            if end_ts is not None and ts > end_ts:
                continue
            observations.append({
                "timestamp": ts,
                "offset_sec": max(0, ts - (start_ts or ts)),
                "price": close,
                "volume": volume,
                "open": _coerce_float(row[1]),
                "high": _coerce_float(row[2]),
                "low": _coerce_float(row[3]),
                "close": close,
            })
        observations.sort(key=lambda item: item["timestamp"])
        return observations

    def _fetch_geckoterminal_pool_ohlcv(
        self,
        *,
        pool_address: str,
        start_ts: int | None,
        end_ts: int | None,
        interval_sec: int,
    ) -> dict[str, Any]:
        network = str(self.provider_config.get("network") or "solana")
        aggregate = self._aggregate_for_interval(interval_sec)
        limit = min(int(self.provider_config.get("max_ohlcv_limit") or 1000), 1000)
        endpoint = str(self.provider_config.get("pair_endpoint") or "networks/{network}/pools/{pool_address}/ohlcv/{timeframe}").format(
            network=network,
            pool_address=pool_address,
            timeframe="minute",
        )
        before_timestamp = end_ts
        all_rows: list[Any] = []
        request_count = 0
        http_status = None
        provider_error_message = None
        warning = None

        while True:
            request_count += 1
            response = self._get(
                endpoint,
                {
                    "aggregate": aggregate,
                    "before_timestamp": before_timestamp,
                    "limit": limit,
                    "currency": self.provider_config.get("currency") or "usd",
                    "token": self.provider_config.get("token") or self.provider_config.get("token_side") or "base",
                    "include_empty_intervals": str(bool(self.provider_config.get("include_empty_intervals", True))).lower(),
                },
            )
            http_status = response.get("http_status") if response.get("http_status") is not None else http_status
            payload = response.get("json")
            ohlcv_rows = _nested_get(payload, "data", "attributes", "ohlcv_list")
            if not isinstance(ohlcv_rows, list):
                ohlcv_rows = []
            all_rows.extend(ohlcv_rows)

            if response.get("http_status") == 429:
                warning = "provider_rate_limited"
                provider_error_message = "provider_rate_limited"
                break
            if response.get("http_status") and int(response["http_status"]) >= 400:
                warning = "provider_http_error"
                provider_error_message = str(_nested_get(payload, "error") or _nested_get(payload, "message") or payload)
                break
            if not ohlcv_rows:
                break

            min_ts = min(_coerce_int(row[0]) or 0 for row in ohlcv_rows)
            if start_ts is None or not min_ts or min_ts <= start_ts or len(ohlcv_rows) < limit:
                break
            before_timestamp = max(0, min_ts - aggregate * 60)

        observations = self._normalize_geckoterminal_ohlcv_list(all_rows, start_ts=start_ts, end_ts=end_ts)
        if not observations and warning is None:
            warning = "no_pool_ohlcv_rows"

        return {
            "rows": observations,
            "provider_row_count": len(observations),
            "request_count": request_count,
            "http_status": http_status,
            "warning": warning,
            "provider_error_message": provider_error_message,
            "aggregate": aggregate,
            "timeframe": "minute",
        }

    def _fetch_legacy_price_history(
        self,
        *,
        token_address: str,
        pair_address: str | None,
        start_ts: int | None,
        end_ts: int | None,
        interval_sec: int,
        limit: int,
    ) -> dict[str, Any]:
        response = self._get(
            str(self.provider_config.get("endpoint") or "price-history"),
            {
                "token_address": token_address,
                "pair_address": pair_address or "",
                "start_ts": start_ts or "",
                "end_ts": end_ts or "",
                "interval_sec": interval_sec,
                "limit": limit,
            },
        )
        payload = response.get("json")
        rows = payload if isinstance(payload, list) else []
        truncated = False
        missing = False
        warning = None
        if isinstance(payload, dict):
            if isinstance(payload.get("rows"), list):
                rows = payload["rows"]
            elif isinstance(payload.get("items"), list):
                rows = payload["items"]
            elif isinstance(payload.get("observations"), list):
                rows = payload["observations"]
            truncated = bool(payload.get("truncated"))
            missing = bool(payload.get("missing"))
            warning = payload.get("warning")

        observations = self._normalize_observations(rows, start_ts=start_ts)
        if not observations:
            missing = True
        if end_ts is not None and observations and observations[-1]["timestamp"] < int(end_ts):
            truncated = True
            warning = warning or "price_path_incomplete"
        return {
            "observations": observations,
            "truncated": truncated,
            "missing": missing,
            "warning": warning,
            "http_status": response.get("http_status"),
            "provider_error_message": None,
            "provider_row_count": len(observations),
        }

    def fetch_price_path(
        self,
        *,
        token_address: str,
        pair_address: str | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
        interval_sec: int = 60,
        limit: int = 256,
    ) -> dict[str, Any]:
        if self.provider == "geckoterminal_pool_ohlcv":
            pool_resolution_status = "seed_pair_address" if pair_address else None
            resolver_result = {
                "pool_address": pair_address or None,
                "resolver_source": "seed_pair_address" if pair_address else str(self.provider_config.get("pool_resolver") or "geckoterminal"),
                "resolver_confidence": "hint" if pair_address else "none",
                "pool_candidates_seen": 1 if pair_address else 0,
                "pool_resolution_status": pool_resolution_status or "pending",
                "http_status": None,
            }
            if not pair_address:
                resolver_result = self._resolve_geckoterminal_pool(token_address, network=str(self.provider_config.get("network") or "solana"))
                pair_address = resolver_result.get("pool_address")
                pool_resolution_status = resolver_result.get("pool_resolution_status")

            if not pair_address:
                return {
                    "token_address": token_address,
                    "pair_address": None,
                    "pool_address": None,
                    "selected_pool_address": None,
                    "source_provider": self.provider,
                    "requested_start_ts": start_ts,
                    "requested_end_ts": end_ts,
                    "interval_sec": interval_sec,
                    "price_path": [],
                    "truncated": False,
                    "missing": True,
                    "price_path_status": "missing",
                    "warning": "pool_resolution_failed",
                    "http_status": resolver_result.get("http_status"),
                    "provider_error_message": None,
                    "provider_row_count": 0,
                    "provider_request_summary": self._provider_request_summary({"limit": limit}),
                    "pool_resolver_source": resolver_result.get("resolver_source"),
                    "pool_resolver_confidence": resolver_result.get("resolver_confidence"),
                    "pool_candidates_seen": resolver_result.get("pool_candidates_seen"),
                    "pool_resolution_status": "pool_resolution_failed",
                }

            ohlcv_result = self._fetch_geckoterminal_pool_ohlcv(
                pool_address=pair_address,
                start_ts=start_ts,
                end_ts=end_ts,
                interval_sec=interval_sec,
            )
            observations = list(ohlcv_result["rows"])
            missing = not observations
            truncated = False
            if observations and end_ts is not None and observations[-1]["timestamp"] < int(end_ts):
                truncated = True
            status = "missing" if missing else "partial" if truncated else "complete"
            warning = ohlcv_result.get("warning")
            if missing and warning is None:
                warning = "no_pool_ohlcv_rows"
            return {
                "token_address": token_address,
                "pair_address": pair_address,
                "pool_address": pair_address,
                "selected_pool_address": pair_address,
                "source_provider": self.provider,
                "requested_start_ts": start_ts,
                "requested_end_ts": end_ts,
                "interval_sec": interval_sec,
                "price_path": observations,
                "truncated": truncated,
                "missing": missing,
                "price_path_status": status,
                "warning": warning,
                "http_status": ohlcv_result.get("http_status"),
                "provider_error_message": ohlcv_result.get("provider_error_message"),
                "provider_row_count": ohlcv_result.get("provider_row_count", len(observations)),
                "provider_request_summary": self._provider_request_summary({
                    "limit": limit,
                    "aggregate": ohlcv_result.get("aggregate"),
                    "timeframe": ohlcv_result.get("timeframe"),
                }),
                "pool_resolver_source": resolver_result.get("resolver_source"),
                "pool_resolver_confidence": resolver_result.get("resolver_confidence"),
                "pool_candidates_seen": resolver_result.get("pool_candidates_seen"),
                "pool_resolution_status": pool_resolution_status or resolver_result.get("pool_resolution_status") or "resolved",
            }

        legacy = self._fetch_legacy_price_history(
            token_address=token_address,
            pair_address=pair_address,
            start_ts=start_ts,
            end_ts=end_ts,
            interval_sec=interval_sec,
            limit=limit,
        )
        status = "complete"
        if legacy["missing"]:
            status = "missing"
        elif legacy["truncated"]:
            status = "partial"

        return {
            "token_address": token_address,
            "pair_address": pair_address,
            "source_provider": self.provider,
            "requested_start_ts": start_ts,
            "requested_end_ts": end_ts,
            "interval_sec": interval_sec,
            "price_path": legacy["observations"],
            "truncated": legacy["truncated"],
            "missing": legacy["missing"],
            "price_path_status": status,
            "warning": legacy["warning"],
            "http_status": legacy["http_status"],
            "provider_error_message": legacy["provider_error_message"],
            "provider_row_count": legacy["provider_row_count"],
            "provider_request_summary": self._provider_request_summary({"limit": limit}),
        }
