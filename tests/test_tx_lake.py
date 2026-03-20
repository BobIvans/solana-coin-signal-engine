from __future__ import annotations

from pathlib import Path

from data.tx_lake import get_tx_lake_status, list_tx_lake_batches, load_tx_batch, resolve_tx_lake_path, write_tx_batch
from data.tx_normalizer import normalize_tx_batch


def test_resolve_tx_lake_path_is_deterministic_for_same_lookup_key(tmp_path: Path):
    first = resolve_tx_lake_path(lookup_key="pair-1", lookup_type="pair_address", provider="helius", root_dir=tmp_path)
    second = resolve_tx_lake_path(lookup_key="pair-1", lookup_type="pair_address", provider="helius", root_dir=tmp_path)
    assert first == second


def test_write_load_and_list_tx_batches(tmp_path: Path):
    batch = normalize_tx_batch(
        [{"signature": "sig-1", "timestamp": 1_710_000_000, "slot": 101, "nativeTransfers": []}],
        source_provider="helius",
        lookup_key="pair-1",
        lookup_type="pair_address",
    )
    path = write_tx_batch(batch, root_dir=tmp_path)
    loaded = load_tx_batch(path=path)
    assert loaded is not None
    assert loaded["tx_batch_record_count"] == 1
    status = get_tx_lake_status(lookup_key="pair-1", lookup_type="pair_address", provider="helius", root_dir=tmp_path)
    assert status["tx_batch_status"] in {"usable", "partial"}
    listed = list_tx_lake_batches(root_dir=tmp_path)
    assert len(listed) == 1
    assert listed[0]["path"] == str(path)


def test_malformed_file_is_reported_without_exception(tmp_path: Path):
    path = resolve_tx_lake_path(lookup_key="pair-2", lookup_type="pair_address", provider="helius", root_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    loaded = load_tx_batch(path=path)
    assert loaded is not None
    assert loaded["tx_batch_status"] == "malformed"
