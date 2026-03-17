from src.calibration.splits import build_day_splits


def test_day_split_non_overlap_and_ordering():
    manifest = {"run_id": "smoke"}
    signals = [{"timestamp_utc": f"2026-03-{day:02d}T01:00:00Z"} for day in range(1, 8)]
    trades = [{"entry_time_utc": f"2026-03-{day:02d}T02:00:00Z"} for day in range(1, 8)]
    config = {"splits": {"train_days": 5, "validation_days": 2}}

    split = build_day_splits(manifest, signals, trades, config)

    assert len(split["train_days"]) == 5
    assert len(split["validation_days"]) == 2
    assert not set(split["train_days"]).intersection(split["validation_days"])
    assert max(split["train_days"]) < min(split["validation_days"])
