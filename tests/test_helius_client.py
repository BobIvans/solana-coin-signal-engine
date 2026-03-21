from __future__ import annotations

from collectors.helius_client import HeliusClient


class StubHeliusClient(HeliusClient):
    def __init__(self, responses, **kwargs):
        super().__init__(api_key="test", **kwargs)
        self._responses = list(responses)
        self.queries = []

    def _get(self, endpoint: str, params: dict[str, object]):
        self.queries.append((endpoint, dict(params)))
        if not self._responses:
            return []
        return self._responses.pop(0)


def test_get_transactions_by_address_with_status_paginates_with_before_until_window_reached(tmp_path):
    client = StubHeliusClient(
        [
            [
                {"signature": "sig_3", "timestamp": 1200, "tokenTransfers": [{"mint": "mint"}]},
                {"signature": "sig_2", "timestamp": 1100, "tokenTransfers": [{"mint": "mint"}]},
            ],
            [
                {"signature": "sig_1", "timestamp": 995, "tokenTransfers": [{"mint": "mint"}]},
            ],
        ],
        tx_lake_dir=str(tmp_path),
    )

    result = client.get_transactions_by_address_with_status("wallet_a", limit=2, fetch_all=True, stop_ts=1000)

    assert len(result["records"]) == 3
    assert result["tx_batch_pages_loaded"] == 2
    assert result["tx_fetch_mode"] == "refresh_required"
    assert client.queries[1][1]["before"] == "sig_2"


def test_get_transactions_by_address_without_fetch_all_stops_after_first_page(tmp_path):
    client = StubHeliusClient(
        [
            [
                {"signature": "sig_3", "timestamp": 1200, "tokenTransfers": [{"mint": "mint"}]},
                {"signature": "sig_2", "timestamp": 1100, "tokenTransfers": [{"mint": "mint"}]},
            ],
            [
                {"signature": "sig_1", "timestamp": 995, "tokenTransfers": [{"mint": "mint"}]},
            ],
        ],
        tx_lake_dir=str(tmp_path),
    )

    result = client.get_transactions_by_address_with_status("wallet_a", limit=2, fetch_all=False, stop_ts=1000)

    assert len(result["records"]) == 2
    assert result["tx_batch_pages_loaded"] == 1
    assert len(client.queries) == 1


def test_helius_client_uses_session_for_rpc_get_and_post():
    class _Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

    class _SessionRecorder:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, timeout=None):
            self.calls.append(("post", url, json, timeout))
            if isinstance(json, dict) and json.get("method"):
                return _Response({"result": {"ok": True}})
            return _Response({"ok": True})

        def get(self, url, params=None, timeout=None):
            self.calls.append(("get", url, params, timeout))
            return _Response({"ok": True})

    session = _SessionRecorder()
    client = HeliusClient(api_key="test", session=session)

    assert client.session is session
    assert client._rpc("getAsset", ["mint"]) == {"ok": True}
    assert client._get("addresses/wallet/transactions", {"limit": 1}) == {"ok": True}
    assert client._post("transactions", {"transactions": ["sig"]}) == {"ok": True}
    assert [call[0] for call in session.calls] == ["post", "get", "post"]
