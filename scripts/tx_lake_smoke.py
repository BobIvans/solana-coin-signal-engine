from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.tx_cache_policy import classify_tx_batch_freshness
from data.tx_lake import get_tx_lake_status, load_tx_batch, make_tx_lake_event, write_tx_batch
from data.tx_normalizer import normalize_tx_batch

RAW_FIXTURE = [
    {
        "signature": "sig-1",
        "timestamp": 1_710_000_000,
        "slot": 101,
        "feePayer": "payer-1",
        "nativeTransfers": [{"fromUserAccount": "payer-1", "toUserAccount": "lp-1", "amount": 1200000000}],
        "tokenTransfers": [{"fromUserAccount": "lp-1", "toUserAccount": "buyer-1", "tokenAmount": 25.0, "mint": "mint-1"}],
        "success": True,
        "liquidity_usd": 2500.0,
    },
    {
        "signature": "sig-2",
        "timestamp": 1_710_000_010,
        "slot": 102,
        "feePayer": "payer-2",
        "nativeTransfers": [{"fromUserAccount": "payer-2", "toUserAccount": "lp-1", "amount": 500000000}],
        "tokenTransfers": [{"fromUserAccount": "lp-1", "toUserAccount": "buyer-2", "tokenAmount": 10.0, "mint": "mint-1"}],
        "success": True,
        "bundle_id": "bundle-1",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lake-dir", default="data/cache/tx_batches")
    parser.add_argument("--smoke-dir", default="data/smoke")
    args = parser.parse_args()

    lake_dir = Path(args.lake_dir)
    smoke_dir = Path(args.smoke_dir)
    smoke_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict[str, object]] = []
    events.append(make_tx_lake_event("tx_lake_lookup_started", lookup_key="pair-smoke", provider="helius", lookup_type="pair_address"))

    batch = normalize_tx_batch(
        RAW_FIXTURE,
        source_provider="helius",
        lookup_key="pair-smoke",
        lookup_type="pair_address",
        tx_batch_origin="smoke_fixture",
        tx_batch_freshness="fresh_cache",
    )
    events.append(make_tx_lake_event("tx_batch_normalized", lookup_key="pair-smoke", provider="helius", record_count=batch.get("record_count"), batch_status=batch.get("tx_batch_status")))

    path = write_tx_batch(batch, root_dir=lake_dir)
    events.append(make_tx_lake_event("tx_batch_written", lookup_key="pair-smoke", provider="helius", path=str(path), record_count=batch.get("record_count")))

    loaded = load_tx_batch(path=path)
    status = get_tx_lake_status(lookup_key="pair-smoke", lookup_type="pair_address", provider="helius", root_dir=lake_dir)
    freshness = classify_tx_batch_freshness(loaded)
    events.append(make_tx_lake_event("tx_lake_cache_hit", lookup_key="pair-smoke", provider="helius", freshness=freshness.get("freshness"), record_count=loaded.get("record_count") if isinstance(loaded, dict) else 0))

    summary = {
        "tx_batch_path": str(path),
        "record_count": int((loaded or {}).get("record_count") or 0),
        "tx_batch_status": (loaded or {}).get("tx_batch_status"),
        "freshness": freshness.get("freshness"),
        "lookup_key": (loaded or {}).get("lookup_key"),
    }

    (smoke_dir / "tx_lake_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (smoke_dir / "tx_lake_status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (smoke_dir / "tx_lake_events.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
