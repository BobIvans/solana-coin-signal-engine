"""Thin Solana RPC client wrappers used by on-chain enrichment."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class SolanaRpcClient:
    def __init__(self, rpc_url: str, commitment: str = "confirmed") -> None:
        self.rpc_url = rpc_url
        self.commitment = commitment

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

    def get_signatures_for_address(self, address: str, limit: int = 40) -> list[dict[str, Any]]:
        result = self._rpc("getSignaturesForAddress", [address, {"limit": limit, "commitment": self.commitment}])
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]
    def get_multiple_accounts(self, pubkeys: list[str]) -> dict[str, Any]:
        keys = [str(key) for key in pubkeys if str(key).strip()][:100]
        if not keys:
            return {"value": []}
        result = self._rpc("getMultipleAccounts", [keys, {"encoding": "jsonParsed", "commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": []}

    def get_token_account_balance(self, token_account: str) -> dict[str, Any]:
        result = self._rpc("getTokenAccountBalance", [token_account, {"commitment": self.commitment}])
        return result if isinstance(result, dict) else {"value": {"amount": "0", "decimals": 0, "uiAmount": 0.0}}

