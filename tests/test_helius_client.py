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
