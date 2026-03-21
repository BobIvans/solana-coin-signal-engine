from __future__ import annotations

from collectors.helius_client import HeliusClient
from collectors.solana_rpc_client import SolanaRpcClient


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *, get_payload=None, post_payload=None, get_status=200, post_status=200):
        self.get_payload = get_payload if get_payload is not None else {}
        self.post_payload = post_payload if post_payload is not None else {}
        self.get_status = get_status
        self.post_status = post_status
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("get", url, params, timeout))
        return FakeResponse(self.get_payload, self.get_status)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("post", url, json, timeout))
        return FakeResponse(self.post_payload, self.post_status)


def test_solana_rpc_client_uses_injected_session():
    session = FakeSession(post_payload={"result": {"value": []}})
    client = SolanaRpcClient("https://rpc.example", session=session)
    result = client.get_multiple_accounts(["abc"])

    assert result == {"value": []}
    assert session.calls
    assert session.calls[0][0] == "post"


def test_helius_client_uses_injected_session():
    session = FakeSession(get_payload=[])
    client = HeliusClient("test-key", session=session)
    result = client.get_transactions_by_address("wallet_a", limit=5)

    assert isinstance(result, list)
    assert session.calls
    assert session.calls[0][0] == "get"


def test_session_http_errors_return_none_not_raise():
    session = FakeSession(post_payload={}, post_status=500)
    client = SolanaRpcClient("https://rpc.example", session=session)
    result = client._rpc("getHealth", [])

    assert result is None
