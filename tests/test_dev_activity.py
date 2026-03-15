import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.dev_activity import compute_dev_sell_pressure_5m, infer_dev_wallet


def test_infer_dev_wallet_prefers_context_wallets():
    inferred = infer_dev_wallet({"creator_wallet": "Dev111"}, [])
    assert inferred["dev_wallet_est"] == "Dev111"
    assert inferred["dev_wallet_confidence_score"] >= 0.7


def test_compute_dev_sell_pressure_uses_5m_window():
    txs = [
        {
            "timestamp": 1_000,
            "tokenTransfers": [
                {"fromUserAccount": "Dev111", "toUserAccount": "A", "tokenAmount": 20},
                {"fromUserAccount": "B", "toUserAccount": "Dev111", "tokenAmount": 100},
            ],
            "accountData": [{"account": "Buyer1", "tokenBalanceChanges": 10}],
        }
    ]
    metrics = compute_dev_sell_pressure_5m("Dev111", {"pair_created_at": "1970-01-01T00:16:40Z"}, txs)
    assert metrics["dev_sell_pressure_5m"] == 0.2
    assert metrics["unique_buyers_5m"] == 1
