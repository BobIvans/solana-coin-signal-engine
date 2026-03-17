"""Deterministic replay train/validation splits."""

from __future__ import annotations

from datetime import datetime


def _extract_day(row: dict) -> str:
    ts = row.get("timestamp") or row.get("timestamp_utc") or row.get("entry_time_utc")
    if not ts:
        raise ValueError("row missing timestamp field")
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()


def build_day_splits(manifest: dict, signals: list[dict], trades: list[dict], config: dict) -> dict:
    splits_cfg = config.get("splits", {})
    train_days = int(splits_cfg.get("train_days", 5))
    validation_days = int(splits_cfg.get("validation_days", 2))

    all_rows = list(signals) + list(trades)
    if not all_rows:
        raise ValueError("cannot build day splits: replay artifacts are empty")

    unique_days = sorted({_extract_day(row) for row in all_rows})
    required_days = train_days + validation_days
    if len(unique_days) < required_days:
        raise ValueError(f"cannot build day splits: need at least {required_days} days, got {len(unique_days)}")

    train = unique_days[:train_days]
    validation = unique_days[train_days : train_days + validation_days]

    if set(train).intersection(validation):
        raise ValueError("train and validation splits overlap")
    if train and validation and max(train) >= min(validation):
        raise ValueError("validation days must be after train days")

    return {
        "train_days": train,
        "validation_days": validation,
        "mode": splits_cfg.get("mode", "by_day"),
        "manifest_run_id": manifest.get("run_id"),
    }
