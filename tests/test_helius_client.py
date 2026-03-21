from __future__ import annotations

from pathlib import Path

from collectors.helius_client import HeliusClient


class FakePaginatedHeliusClient(HeliusClient):
    def __init__(self, *args, pages=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = pages or {}
        self.calls: list[dict] = []

    def _get(self, endpoint, params):
        self.calls.append(dict(params))
        return self.pages.get(params.get("before"))



def test_helius_client_paginates_until_launch_window_is_reached(tmp_path: Path):
    pages = {
        None: [
            {"signature": "sig-3", "timestamp": 1300, "slot": 13, "nativeTransfers": []},
            {"signature": "sig-2", "timestamp": 1200, "slot": 12, "nativeTransfers": []},
        ],
        "sig-2": [
            {"signature": "sig-1", "timestamp": 1100, "slot": 11, "nativeTransfers": []},
            {"signature": "sig-0", "timestamp": 1000, "slot": 10, "nativeTransfers": []},
        ],
        "sig-0": [
            {"signature": "sig--1", "timestamp": 900, "slot": 9, "nativeTransfers": []},
        ],
    }
    client = FakePaginatedHeliusClient("demo", tx_lake_dir=str(tmp_path), pages=pages)

    result = client.get_transactions_by_address_with_status(
        "pair-1",
        limit=2,
        pair_created_at_ts=950,
        max_pages=3,
    )

    assert len(client.calls) == 3
    assert result["tx_batch_record_count"] == 5
    assert result["historical_window_reached"] is True
    assert result["pagination_pages_fetched"] == 3
    assert result["records"][-1]["timestamp"] == 900



def test_helius_client_marks_partial_when_page_budget_stops_early(tmp_path: Path):
    pages = {
        None: [
            {"signature": "sig-3", "timestamp": 1300, "slot": 13, "nativeTransfers": []},
            {"signature": "sig-2", "timestamp": 1200, "slot": 12, "nativeTransfers": []},
        ],
        "sig-2": [
            {"signature": "sig-1", "timestamp": 1100, "slot": 11, "nativeTransfers": []},
            {"signature": "sig-0", "timestamp": 1000, "slot": 10, "nativeTransfers": []},
        ],
    }
    client = FakePaginatedHeliusClient("demo", tx_lake_dir=str(tmp_path), pages=pages)

    result = client.get_transactions_by_address_with_status(
        "pair-2",
        limit=2,
        pair_created_at_ts=900,
        max_pages=1,
    )

    assert len(client.calls) == 1
    assert result["tx_batch_status"] == "partial"
    assert result["historical_window_reached"] is False
