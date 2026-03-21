"""Canonical historical price-path collection helpers for replay backfill."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen



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


class PriceHistoryClient:
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, provider: str = "price_history") -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.provider = provider

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        if not self.base_url:
            return {"rows": [], "missing": True, "warning": "price_history_provider_unconfigured"}
        query = dict(params)
        if self.api_key:
            query.setdefault("api_key", self.api_key)
        req = Request(
            f"{self.base_url}/{endpoint}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": "scse/0.1"},
        )
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return {"rows": [], "missing": True, "warning": "price_history_request_failed"}

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
        payload = self._get(
            "price-history",
            {
                "token_address": token_address,
                "pair_address": pair_address or "",
                "start_ts": start_ts or "",
                "end_ts": end_ts or "",
                "interval_sec": interval_sec,
                "limit": limit,
            },
        )
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

        status = "complete"
        if missing:
            status = "missing"
        elif truncated:
            status = "partial"

        return {
            "token_address": token_address,
            "pair_address": pair_address,
            "source_provider": self.provider,
            "requested_start_ts": start_ts,
            "requested_end_ts": end_ts,
            "interval_sec": interval_sec,
            "price_path": observations,
            "truncated": truncated,
            "missing": missing,
            "price_path_status": status,
            "warning": warning,
        }
