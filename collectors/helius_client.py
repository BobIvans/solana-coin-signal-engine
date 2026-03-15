"""Helius API wrappers for DAS and enhanced transactions."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HeliusClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        self.base_url = "https://api.helius.xyz/v0"

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

    def get_transactions_by_address(self, address: str, limit: int = 40) -> list[dict[str, Any]]:
        result = self._get(f"addresses/{address}/transactions", {"limit": limit})
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    def get_transactions_by_signatures(self, signatures: list[str]) -> list[dict[str, Any]]:
        if not signatures:
            return []
        result = self._post("transactions", {"transactions": signatures})
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]
